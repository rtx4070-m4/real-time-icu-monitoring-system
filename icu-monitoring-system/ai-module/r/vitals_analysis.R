#!/usr/bin/env Rscript
# R Statistical Analysis Module for ICU Monitoring System
# Performs time-series analysis, trend detection, and population-level statistics
# Exposes results via Plumber REST API

library(plumber)
library(jsonlite)
library(dplyr)
library(tidyr)
library(ggplot2)
library(forecast)    # ARIMA time-series forecasting
library(tseries)     # ADF test for stationarity
library(changepoint) # Structural break detection (PELT algorithm)
library(httr)

# ── Statistical Analysis Functions ────────────────────────────────────────────

#' Compute enhanced vital statistics for a single patient's history
#' @param vitals_df Data frame with columns: timestamp, heart_rate, spo2, systolic_bp, etc.
compute_vital_stats <- function(vitals_df) {
  if (nrow(vitals_df) < 3) {
    return(list(error = "Insufficient data (need >= 3 observations)"))
  }

  stats_for <- function(col_name) {
    x <- vitals_df[[col_name]]
    x <- x[!is.na(x)]
    if (length(x) == 0) return(NULL)

    # Mann-Kendall trend test (monotonic trend detection)
    mk_p_val <- tryCatch({
      kt <- cor.test(seq_along(x), x, method = "kendall")
      kt$p.value
    }, error = function(e) NA_real_)

    trend_dir <- if (!is.na(mk_p_val) && mk_p_val < 0.05) {
      if (tail(x, 1) > x[1]) "INCREASING" else "DECREASING"
    } else {
      "STABLE"
    }

    list(
      mean      = round(mean(x), 2),
      sd        = round(sd(x), 2),
      min       = round(min(x), 2),
      max       = round(max(x), 2),
      median    = round(median(x), 2),
      iqr       = round(IQR(x), 2),
      trend     = trend_dir,
      trend_p   = round(mk_p_val, 4),
      cv        = round(sd(x) / mean(x) * 100, 2)  # Coefficient of variation
    )
  }

  list(
    heart_rate       = stats_for("heart_rate"),
    systolic_bp      = stats_for("systolic_bp"),
    spo2             = stats_for("spo2"),
    respiratory_rate = stats_for("respiratory_rate"),
    temperature      = stats_for("temperature"),
    lactate          = stats_for("lactate"),
    n_observations   = nrow(vitals_df)
  )
}

#' Detect structural breakpoints in a vital sign time series
#' Uses the PELT (Pruned Exact Linear Time) algorithm
#' @param values Numeric vector of vital sign values
#' @param vital_name Name of the vital for labeling
detect_changepoints <- function(values, vital_name = "vital") {
  if (length(values) < 6) {
    return(list(changepoints = list(), n_segments = 1))
  }

  tryCatch({
    # PELT with Normal penalty
    result <- cpt.mean(values, method = "PELT", penalty = "BIC")
    cpts   <- cpts(result)

    list(
      vital        = vital_name,
      changepoints = as.list(cpts),
      n_segments   = length(cpts) + 1,
      segment_means = lapply(
        split(values, findInterval(seq_along(values), cpts)),
        mean
      )
    )
  }, error = function(e) {
    list(changepoints = list(), n_segments = 1, error = conditionMessage(e))
  })
}

#' ARIMA forecast for a vital sign (next N observations)
#' @param values Numeric time series
#' @param n_ahead Number of steps to forecast
arima_forecast <- function(values, n_ahead = 5) {
  if (length(values) < 10) {
    return(list(error = "Need at least 10 observations for ARIMA"))
  }

  tryCatch({
    ts_data <- ts(values, frequency = 1)

    # Check stationarity
    adf_result <- adf.test(ts_data)
    is_stationary <- adf_result$p.value < 0.05

    # Auto-fit ARIMA
    fit    <- auto.arima(ts_data, stepwise = TRUE, approximation = TRUE)
    fcast  <- forecast(fit, h = n_ahead)

    list(
      model         = as.character(fit),
      is_stationary = is_stationary,
      adf_p_value   = round(adf_result$p.value, 4),
      forecast_mean = round(as.numeric(fcast$mean), 2),
      lower_95      = round(as.numeric(fcast$lower[, "95%"]), 2),
      upper_95      = round(as.numeric(fcast$upper[, "95%"]), 2),
      aic           = round(fit$aic, 2),
      n_ahead       = n_ahead
    )
  }, error = function(e) {
    list(error = conditionMessage(e))
  })
}

#' Population-level statistical comparison across all ICU patients
#' Identifies outlier patients based on Mahalanobis distance
population_analysis <- function(all_vitals_list) {
  if (length(all_vitals_list) < 2) {
    return(list(error = "Need at least 2 patients for population analysis"))
  }

  # Summarise each patient to a feature row
  patient_summaries <- lapply(all_vitals_list, function(pv) {
    data.frame(
      patient_id = pv$patient_id,
      hr_mean    = mean(pv$heart_rate,       na.rm = TRUE),
      sbp_mean   = mean(pv$systolic_bp,      na.rm = TRUE),
      spo2_mean  = mean(pv$spo2,             na.rm = TRUE),
      rr_mean    = mean(pv$respiratory_rate, na.rm = TRUE),
      temp_mean  = mean(pv$temperature,      na.rm = TRUE),
      lact_mean  = mean(pv$lactate,          na.rm = TRUE)
    )
  })

  summary_df <- bind_rows(patient_summaries)
  feature_cols <- c("hr_mean", "sbp_mean", "spo2_mean", "rr_mean", "temp_mean", "lact_mean")
  feature_matrix <- as.matrix(summary_df[, feature_cols])

  # Mahalanobis distance for outlier detection
  tryCatch({
    center <- colMeans(feature_matrix)
    cov_mx <- cov(feature_matrix)

    # Add small regularization to handle near-singular covariance
    cov_mx <- cov_mx + diag(1e-6, ncol(cov_mx))

    m_dist <- mahalanobis(feature_matrix, center, cov_mx)
    threshold <- qchisq(0.975, df = ncol(feature_matrix))

    outlier_flags <- m_dist > threshold

    list(
      n_patients          = nrow(summary_df),
      mahalanobis_dist    = round(m_dist, 3),
      threshold           = round(threshold, 3),
      outlier_patients    = summary_df$patient_id[outlier_flags],
      population_means    = round(colMeans(feature_matrix), 2),
      population_sds      = round(apply(feature_matrix, 2, sd), 2)
    )
  }, error = function(e) {
    list(error = conditionMessage(e))
  })
}

# ── Plumber REST API ──────────────────────────────────────────────────────────

#* @apiTitle ICU Statistical Analysis API (R)
#* @apiDescription Time-series analysis, ARIMA forecasting, and population statistics

#* Health check
#* @get /health
function() {
  list(status = "healthy", language = "R", version = R.version$version.string)
}

#* Patient vital statistics
#* @param patient_id Patient identifier
#* @param vitals_json JSON array of vitals observations
#* @post /api/v1/stats
function(req, res) {
  tryCatch({
    body <- fromJSON(rawToChar(req$bodyRaw), simplifyDataFrame = TRUE)
    vitals_df <- as.data.frame(body$vitals)
    stats <- compute_vital_stats(vitals_df)
    toJSON(stats, auto_unbox = TRUE)
  }, error = function(e) {
    res$status <- 400
    list(error = conditionMessage(e))
  })
}

#* Detect changepoints in vital signs
#* @post /api/v1/changepoints
function(req, res) {
  tryCatch({
    body <- fromJSON(rawToChar(req$bodyRaw), simplifyDataFrame = FALSE)
    values <- as.numeric(body$values)
    vital  <- body$vital_name %||% "vital"
    result <- detect_changepoints(values, vital)
    toJSON(result, auto_unbox = TRUE)
  }, error = function(e) {
    res$status <- 400
    list(error = conditionMessage(e))
  })
}

#* ARIMA forecast for a vital sign
#* @post /api/v1/forecast
function(req, res) {
  tryCatch({
    body    <- fromJSON(rawToChar(req$bodyRaw), simplifyDataFrame = FALSE)
    values  <- as.numeric(body$values)
    n_ahead <- as.integer(body$n_ahead %||% 5)
    result  <- arima_forecast(values, n_ahead)
    toJSON(result, auto_unbox = TRUE)
  }, error = function(e) {
    res$status <- 400
    list(error = conditionMessage(e))
  })
}

#* Population-level analysis across all patients
#* @post /api/v1/population
function(req, res) {
  tryCatch({
    body   <- fromJSON(rawToChar(req$bodyRaw), simplifyDataFrame = FALSE)
    result <- population_analysis(body$patients)
    toJSON(result, auto_unbox = TRUE)
  }, error = function(e) {
    res$status <- 400
    list(error = conditionMessage(e))
  })
}

# Null coalescing helper (R doesn't have ??)
`%||%` <- function(a, b) if (!is.null(a)) a else b

# ── Start server ──────────────────────────────────────────────────────────────
port <- as.integer(Sys.getenv("R_API_PORT", "8083"))
cat(sprintf("Starting ICU R Statistical Analysis API on port %d...\n", port))

pr <- plumber::plumb(file = "vitals_analysis.R")
pr$run(host = "0.0.0.0", port = port)
