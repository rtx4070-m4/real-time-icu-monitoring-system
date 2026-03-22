FROM julia:1.10-bullseye

WORKDIR /app

# Install Julia packages
RUN julia -e 'using Pkg; Pkg.add(["HTTP", "JSON3", "Statistics", "LinearAlgebra", "Dates"])'

COPY kalman_filter.jl .

ENV JULIA_API_PORT=8084
EXPOSE 8084

CMD ["julia", "kalman_filter.jl"]
