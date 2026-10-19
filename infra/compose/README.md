# Local infrastructure only

This Compose stack is development infrastructure. PostgreSQL, Kafka and MinIO
publish only on loopback. Kafka uses plaintext inside this local network; do not
expose the stack through port forwarding or use it as a production deployment.

Set `POSTGRES_PASSWORD` and `AWS_SECRET_ACCESS_KEY` in the local environment or
pass the repository `.env` explicitly with `docker compose --env-file .env -f
infra/compose/docker-compose.yml ...`. No password fallback is supplied. Changing
an environment variable does not rotate credentials in an existing volume; rotate
previously used credentials with the database/storage administration tools.

MinIO images are pinned to the digests installed during the October 18 audit
remediation. PostgreSQL and Kafka retain their version tags. Image pinning is
reproducibility evidence, not a vulnerability scan or production certification.

Production networking, backups/restore, service identities, secret rotation,
storage lifecycle and AWS cost limits remain deployment work. The Helm and
Terraform directories are future scaffolding, not supported deployment artifacts.
The six empty schema/client/policy packages likewise remain roadmap placeholders;
they do not define runtime contracts or have build scripts.
