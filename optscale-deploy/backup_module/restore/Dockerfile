FROM alpine:3.19 AS builder

RUN apk add --no-cache curl bash

# Download ClickHouse static binary
RUN curl https://clickhouse.com/ | sh \
    && mv clickhouse /usr/local/bin/clickhouse \
    && ln -s /usr/local/bin/clickhouse /usr/local/bin/clickhouse-client

FROM alpine:3.19

RUN apk add --no-cache \
    bash \
    curl \
    mariadb-client \
    mongodb-tools \
    aws-cli \
    ca-certificates

COPY --from=builder /usr/local/bin/clickhouse /usr/local/bin/clickhouse
COPY --from=builder /usr/local/bin/clickhouse-client /usr/local/bin/clickhouse-client

COPY restore.sh /usr/local/bin/restore.sh
RUN chmod +x /usr/local/bin/restore.sh

ENTRYPOINT ["/usr/local/bin/restore.sh"]
