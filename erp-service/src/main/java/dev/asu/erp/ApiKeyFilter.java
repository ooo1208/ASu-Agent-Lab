package dev.asu.erp;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class ApiKeyFilter extends OncePerRequestFilter {
    private final byte[] expected;
    private final ObjectMapper mapper;
    public ApiKeyFilter(@Value("${erp.api-key:}") String key, ObjectMapper mapper) {
        this.expected = key.getBytes(StandardCharsets.UTF_8); this.mapper = mapper;
    }
    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain) throws ServletException, IOException {
        if (expected.length > 0 && request.getRequestURI().startsWith("/api/")) {
            String supplied = request.getHeader("X-API-Key");
            if (supplied == null || !MessageDigest.isEqual(expected, supplied.getBytes(StandardCharsets.UTF_8))) {
                response.setStatus(401); response.setContentType("application/json");
                mapper.writeValue(response.getOutputStream(), ApiResponse.error(401, "Valid X-API-Key required")); return;
            }
        }
        chain.doFilter(request, response);
    }
}
