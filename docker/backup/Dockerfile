# Backups for docker-compose.prod.yml (Phase 5.4): pg_dump / pg_restore 16 (same major version as the database),
# age (encryption to a public key; the private key never touches the server) and rclone (S3: the photo bucket and
# the off-site copy). Runs as the unprivileged "postgres" user of the base image.
FROM postgres:16-bookworm
RUN apt-get update \
    && apt-get install -y --no-install-recommends age rclone ca-certificates tar coreutils \
    && rm -rf /var/lib/apt/lists/* \
    && rm -f /usr/local/bin/gosu   # the base image's root-to-postgres helper: unused here (USER postgres), and old Go
COPY --chmod=0755 backup.sh restore.sh schedule.sh /usr/local/bin/
RUN mkdir -p /backups /restore && chown postgres:postgres /backups /restore
USER postgres
WORKDIR /backups
ENTRYPOINT []
CMD ["schedule.sh"]
