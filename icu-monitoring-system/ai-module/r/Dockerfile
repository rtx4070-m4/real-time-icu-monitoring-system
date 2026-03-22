FROM r-base:4.3.2

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libssl-dev \
    libcurl4-openssl-dev \
    libxml2-dev \
    && rm -rf /var/lib/apt/lists/*

# Install R packages
RUN Rscript -e "install.packages(c( \
    'plumber', \
    'jsonlite', \
    'dplyr', \
    'tidyr', \
    'ggplot2', \
    'forecast', \
    'tseries', \
    'changepoint', \
    'httr' \
    ), repos='https://cloud.r-project.org')"

WORKDIR /app
COPY vitals_analysis.R .

ENV R_API_PORT=8083
EXPOSE 8083

CMD ["Rscript", "vitals_analysis.R"]
