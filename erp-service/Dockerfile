FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /build
COPY pom.xml .
COPY src ./src
RUN mvn -B -ntp package

FROM eclipse-temurin:21-jre
WORKDIR /app
RUN useradd --system --uid 10001 --create-home erp && mkdir -p /app/data && chown -R erp:erp /app
COPY --from=build --chown=erp:erp /build/target/erp-service-1.0.0.jar /app/erp.jar
USER erp
ENV ERP_BIND_ADDRESS=0.0.0.0
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/erp.jar"]
