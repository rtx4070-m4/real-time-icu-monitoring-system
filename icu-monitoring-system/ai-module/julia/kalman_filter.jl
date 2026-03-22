# ICU Time-Series Analysis Module – Julia
# Performs high-performance Kalman filtering and state-space modeling on ICU vitals
# Exposes results via HTTP.jl REST endpoints

using HTTP
using JSON3
using Dates
using Statistics
using LinearAlgebra

# ── Kalman Filter for vital sign smoothing and prediction ─────────────────────

"""
    KalmanFilter1D(; process_noise, measurement_noise, initial_state, initial_cov)

Univariate Kalman filter for online vital sign estimation.
- `process_noise`     (Q): variance of the true underlying state transitions
- `measurement_noise` (R): variance of sensor/measurement noise
"""
mutable struct KalmanFilter1D
    Q::Float64       # Process noise covariance
    R::Float64       # Measurement noise covariance
    x::Float64       # State estimate
    P::Float64       # Estimate covariance
    history_x::Vector{Float64}
    history_P::Vector{Float64}
end

function KalmanFilter1D(;
    process_noise::Float64     = 1.0,
    measurement_noise::Float64 = 5.0,
    initial_state::Float64     = 0.0,
    initial_cov::Float64       = 100.0,
)
    KalmanFilter1D(process_noise, measurement_noise, initial_state, initial_cov,
                   Float64[], Float64[])
end

"""Update the Kalman filter with a new measurement and return the filtered estimate."""
function update!(kf::KalmanFilter1D, measurement::Float64)
    # Predict step
    x_pred = kf.x
    P_pred = kf.P + kf.Q

    # Update step
    K    = P_pred / (P_pred + kf.R)   # Kalman gain
    kf.x = x_pred + K * (measurement - x_pred)
    kf.P = (1.0 - K) * P_pred

    push!(kf.history_x, kf.x)
    push!(kf.history_P, kf.P)

    return kf.x
end

"""Predict n steps ahead using current state estimate."""
function predict_ahead(kf::KalmanFilter1D, n::Int)
    x_pred = kf.x
    P_pred = kf.P

    predictions = Float64[]
    uncertainties = Float64[]
    for _ in 1:n
        P_pred += kf.Q
        push!(predictions, x_pred)
        push!(uncertainties, sqrt(P_pred + kf.R))  # 1-sigma prediction interval
    end

    return predictions, uncertainties
end


# ── Multi-vital Kalman state for a patient ────────────────────────────────────

struct PatientKalmanState
    patient_id  :: String
    hr_filter   :: KalmanFilter1D
    bp_filter   :: KalmanFilter1D
    spo2_filter :: KalmanFilter1D
    rr_filter   :: KalmanFilter1D
    temp_filter :: KalmanFilter1D
    lact_filter :: KalmanFilter1D
    created_at  :: DateTime
end

function PatientKalmanState(patient_id::String)
    PatientKalmanState(
        patient_id,
        KalmanFilter1D(process_noise=2.0,  measurement_noise=4.0),   # HR
        KalmanFilter1D(process_noise=3.0,  measurement_noise=6.0),   # BP
        KalmanFilter1D(process_noise=0.1,  measurement_noise=0.5),   # SpO2
        KalmanFilter1D(process_noise=0.5,  measurement_noise=1.5),   # RR
        KalmanFilter1D(process_noise=0.01, measurement_noise=0.04),  # Temp
        KalmanFilter1D(process_noise=0.05, measurement_noise=0.2),   # Lactate
        now(UTC),
    )
end

# Global patient state registry
const PATIENT_STATES = Dict{String, PatientKalmanState}()
const STATE_LOCK = ReentrantLock()


# ── Statistical utility functions ─────────────────────────────────────────────

"""Exponentially weighted moving average (EWMA)."""
function ewma(values::Vector{Float64}; alpha::Float64 = 0.3)
    isempty(values) && return Float64[]
    result = similar(values)
    result[1] = values[1]
    for i in 2:length(values)
        result[i] = alpha * values[i] + (1.0 - alpha) * result[i-1]
    end
    return result
end

"""Compute the rate of change (first differences) normalised by mean."""
function relative_rate_of_change(values::Vector{Float64})
    length(values) < 2 && return 0.0
    diffs = diff(values)
    μ = mean(values)
    μ ≈ 0.0 ? 0.0 : mean(diffs) / abs(μ)
end

"""
Spike detection using a modified Z-score (robust to outliers).
Returns indices of potential artifacts/spikes.
"""
function detect_spikes(values::Vector{Float64}; threshold::Float64 = 3.5)
    isempty(values) && return Int[]
    med = median(values)
    mad = median(abs.(values .- med))
    mad ≈ 0.0 && return Int[]
    m_scores = 0.6745 .* abs.(values .- med) ./ mad
    findall(m_scores .> threshold)
end

"""
Compute sample entropy (ApEn approximation) for regularity analysis.
Lower entropy = more regular (e.g., sinus rhythm vs arrhythmia).
"""
function approximate_entropy(values::Vector{Float64}; m::Int = 2, r_scale::Float64 = 0.2)
    n = length(values)
    n < m + 2 && return NaN
    r = r_scale * std(values)
    r ≈ 0.0 && return 0.0

    count_matches(template_len) = begin
        count = 0
        for i in 1:(n - template_len)
            for j in 1:(n - template_len)
                i == j && continue
                if maximum(abs.(values[i:i+template_len-1] .- values[j:j+template_len-1])) <= r
                    count += 1
                end
            end
        end
        count / (n - template_len)
    end

    cm  = count_matches(m)
    cm1 = count_matches(m + 1)

    (cm > 0 && cm1 > 0) ? log(cm / cm1) : 0.0
end


# ── HTTP API handlers ─────────────────────────────────────────────────────────

"""Process Kalman filter update for a patient."""
function handle_kalman_update(req::HTTP.Request)
    body = JSON3.read(req.body)

    patient_id = get(body, :patient_id, nothing)
    isnothing(patient_id) && return HTTP.Response(400, "Missing patient_id")

    state = lock(STATE_LOCK) do
        get!(PATIENT_STATES, patient_id) do
            PatientKalmanState(patient_id)
        end
    end

    # Apply measurements to each filter
    hr_smooth   = update!(state.hr_filter,   Float64(get(body, :heart_rate,       80.0)))
    bp_smooth   = update!(state.bp_filter,   Float64(get(body, :systolic_bp,     120.0)))
    spo2_smooth = update!(state.spo2_filter, Float64(get(body, :spo2,             97.0)))
    rr_smooth   = update!(state.rr_filter,   Float64(get(body, :respiratory_rate, 16.0)))
    temp_smooth = update!(state.temp_filter, Float64(get(body, :temperature,      37.0)))
    lact_smooth = update!(state.lact_filter, Float64(get(body, :lactate,           1.0)))

    # 5-step ahead predictions
    hr_pred, hr_unc     = predict_ahead(state.hr_filter,   5)
    bp_pred, bp_unc     = predict_ahead(state.bp_filter,   5)
    spo2_pred, spo2_unc = predict_ahead(state.spo2_filter, 5)

    result = Dict(
        :patient_id  => patient_id,
        :smoothed    => Dict(
            :heart_rate       => round(hr_smooth,   digits=2),
            :systolic_bp      => round(bp_smooth,   digits=2),
            :spo2             => round(spo2_smooth, digits=2),
            :respiratory_rate => round(rr_smooth,   digits=2),
            :temperature      => round(temp_smooth, digits=4),
            :lactate          => round(lact_smooth, digits=3),
        ),
        :predictions => Dict(
            :heart_rate  => Dict(:values => round.(hr_pred,   digits=2),
                                 :uncertainty => round.(hr_unc,   digits=2)),
            :systolic_bp => Dict(:values => round.(bp_pred,   digits=2),
                                 :uncertainty => round.(bp_unc,   digits=2)),
            :spo2        => Dict(:values => round.(spo2_pred, digits=2),
                                 :uncertainty => round.(spo2_unc, digits=2)),
        ),
        :filter_confidence => Dict(
            :hr_cov   => round(state.hr_filter.P,   digits=4),
            :bp_cov   => round(state.bp_filter.P,   digits=4),
            :spo2_cov => round(state.spo2_filter.P, digits=4),
        ),
        :timestamp => Dates.format(now(UTC), "yyyy-mm-ddTHH:MM:SSZ"),
    )

    HTTP.Response(200, ["Content-Type" => "application/json"], JSON3.write(result))
end

"""Analyse a time series for spikes, entropy, and EWMA."""
function handle_timeseries_analysis(req::HTTP.Request)
    body   = JSON3.read(req.body)
    values = Float64.(get(body, :values, Float64[]))

    isempty(values) && return HTTP.Response(400, "Missing 'values' array")

    spikes    = detect_spikes(values)
    smoothed  = ewma(values, alpha=0.3)
    roc       = relative_rate_of_change(values)
    apen      = length(values) >= 10 ? approximate_entropy(values) : NaN

    result = Dict(
        :n             => length(values),
        :mean          => round(mean(values),   digits=3),
        :std           => round(std(values),    digits=3),
        :spike_indices => spikes,
        :n_spikes      => length(spikes),
        :ewma_last     => isempty(smoothed) ? nothing : round(last(smoothed), digits=3),
        :rate_of_change => round(roc,  digits=4),
        :approx_entropy => isnan(apen) ? nothing : round(apen, digits=4),
    )

    HTTP.Response(200, ["Content-Type" => "application/json"], JSON3.write(result))
end

"""Health check."""
function handle_health(req::HTTP.Request)
    result = Dict(
        :status   => "healthy",
        :language => "Julia",
        :version  => string(VERSION),
        :patients => length(PATIENT_STATES),
    )
    HTTP.Response(200, ["Content-Type" => "application/json"], JSON3.write(result))
end


# ── Router ────────────────────────────────────────────────────────────────────

function router(req::HTTP.Request)
    path   = req.target
    method = req.method

    if path == "/health" && method == "GET"
        return handle_health(req)
    elseif path == "/api/v1/kalman" && method == "POST"
        return handle_kalman_update(req)
    elseif path == "/api/v1/timeseries" && method == "POST"
        return handle_timeseries_analysis(req)
    else
        return HTTP.Response(404, "Not found: $method $path")
    end
end


# ── Entry point ───────────────────────────────────────────────────────────────

port = parse(Int, get(ENV, "JULIA_API_PORT", "8084"))

println("╔══════════════════════════════════════════════════════╗")
println("║  ICU Kalman Filter Module  –  Julia $(VERSION)       ")
println("╚══════════════════════════════════════════════════════╝")
println("Listening on port $port...")

HTTP.serve(router, "0.0.0.0", port)
