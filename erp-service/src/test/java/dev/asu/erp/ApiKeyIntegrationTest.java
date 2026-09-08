package dev.asu.erp;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties={"erp.api-key=synthetic-test-key", "spring.datasource.url=jdbc:h2:mem:erp-auth-test;MODE=MySQL;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1"})
@AutoConfigureMockMvc @ActiveProfiles("test")
class ApiKeyIntegrationTest {
    @Autowired MockMvc mvc;
    @Test void protectedApiRejectsMissingAndWrongCredentials() throws Exception {
        mvc.perform(get("/api/parts/page")).andExpect(status().isUnauthorized()).andExpect(jsonPath("$.code").value(401));
        mvc.perform(get("/api/parts/page").header("X-API-Key","wrong")).andExpect(status().isUnauthorized());
        mvc.perform(get("/api/parts/page").header("X-API-Key","synthetic-test-key")).andExpect(status().isOk()).andExpect(jsonPath("$.data.total").value(3));
        mvc.perform(get("/actuator/health")).andExpect(status().isOk());
    }
}
