package dev.asu.erp;

import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

@RestControllerAdvice
public class ApiErrors {
    @ExceptionHandler(ApiException.class)
    ResponseEntity<ApiResponse> domain(ApiException error) { return ResponseEntity.status(error.status).body(ApiResponse.error(error.status, error.getMessage())); }
    @ExceptionHandler({HttpMessageNotReadableException.class, MethodArgumentTypeMismatchException.class})
    ResponseEntity<ApiResponse> malformed(Exception error) { return ResponseEntity.badRequest().body(ApiResponse.error(400, "Malformed request or invalid parameter type")); }
    @ExceptionHandler(DataIntegrityViolationException.class)
    ResponseEntity<ApiResponse> duplicate(Exception error) { return ResponseEntity.status(409).body(ApiResponse.error(409, "Duplicate business identifier or invalid database constraint")); }
}
