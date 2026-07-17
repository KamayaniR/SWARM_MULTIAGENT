# swarm-pomerium: Pomerium with our sandbox-ingress config baked in.
# The base image's entrypoint is /bin/pomerium; we point it at the config.
FROM pomerium/pomerium:latest

COPY config.yaml /pomerium/config.yaml

# Akash edge forwards plain HTTP here (TLS terminated upstream). See config.yaml.
EXPOSE 80

CMD ["-config", "/pomerium/config.yaml"]
