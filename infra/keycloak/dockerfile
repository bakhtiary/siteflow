# Stage 1: Build / Optimize Keycloak for production
FROM quay.io/keycloak/keycloak:24.0 as builder

# Enable the health and metrics endpoints, and configure the DB vendor
ENV KC_HEALTH_ENABLED=true
ENV KC_METRICS_ENABLED=true
ENV KC_DB=postgres

RUN /opt/keycloak/bin/kc.sh build

# Stage 2: Final lightweight runner image
FROM quay.io/keycloak/keycloak:24.0
COPY --from=builder /opt/keycloak/ /opt/keycloak/

# Cloud Run defaults to standard HTTP port 8080. Keycloak listens there natively.
EXPOSE 8080

ENTRYPOINT ["/opt/keycloak/bin/kc.sh"]
