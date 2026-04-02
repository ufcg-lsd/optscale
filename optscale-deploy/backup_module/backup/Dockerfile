# Stage 1: Builder
FROM debian:bookworm-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    unzip \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install AWS CLI v2 (installs to /usr/local/aws-cli by default)
RUN curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip" && \
    unzip awscliv2.zip && \
    ./aws/install && \
    rm -rf awscliv2.zip aws

# Download and extract MongoDB tools
RUN curl -LO https://fastdl.mongodb.org/tools/db/mongodb-database-tools-debian12-x86_64-100.10.0.tgz && \
    tar -xzf mongodb-database-tools-debian12-x86_64-100.10.0.tgz && \
    mv mongodb-database-tools-*/bin/* /usr/local/bin/ && \
    rm -rf mongodb-database-tools-*

# Install ClickHouse client (static binary)
RUN curl -LO https://github.com/ClickHouse/ClickHouse/releases/latest/download/clickhouse-client && \
    chmod +x clickhouse-client && \
    mv clickhouse-client /usr/local/bin/clickhouse-client


# Stage 2: Final lightweight image
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    default-mysql-client \
    redis-tools \
    curl \
    ca-certificates \
    bash \
    groff \
    less \
    libgssapi-krb5-2 \
    && rm -rf /var/lib/apt/lists/*

# Copy AWS CLI v2 (full install dir + symlink)
COPY --from=builder /usr/local/aws-cli /usr/local/aws-cli
RUN ln -s /usr/local/aws-cli/v2/current/bin/aws /usr/local/bin/aws

# Copy MongoDB tools
COPY --from=builder /usr/local/bin/mongodump \
                    /usr/local/bin/mongorestore \
                    /usr/local/bin/mongoexport \
                    /usr/local/bin/mongoimport \
                    /usr/local/bin/mongostat \
                    /usr/local/bin/mongotop \
                    /usr/local/bin/bsondump \
                    /usr/local/bin/mongofiles \
                    /usr/local/bin/

# Copy ClickHouse client
COPY --from=builder /usr/local/bin/clickhouse-client /usr/local/bin/clickhouse-client

# Copy backup script
COPY backup.sh /usr/local/bin/backup.sh
RUN chmod +x /usr/local/bin/backup.sh

ENTRYPOINT ["/usr/local/bin/backup.sh"]
