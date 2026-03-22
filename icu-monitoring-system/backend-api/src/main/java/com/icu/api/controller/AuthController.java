package com.icu.api.controller;

import com.icu.api.model.User;
import com.icu.api.repository.UserRepository;
import com.icu.api.security.JwtService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/api/v1/auth")
@RequiredArgsConstructor
@CrossOrigin(origins = "*")
public class AuthController {

    private final AuthenticationManager authenticationManager;
    private final UserRepository        userRepository;
    private final JwtService            jwtService;
    private final PasswordEncoder       passwordEncoder;

    /** POST /api/v1/auth/login */
    @PostMapping("/login")
    public ResponseEntity<Map<String, Object>> login(@RequestBody Map<String, String> body) {
        authenticationManager.authenticate(
            new UsernamePasswordAuthenticationToken(
                body.get("username"),
                body.get("password")
            )
        );

        User user = userRepository.findByUsername(body.get("username"))
            .orElseThrow();

        String token = jwtService.generateToken(user);

        return ResponseEntity.ok(Map.of(
            "token",    token,
            "username", user.getUsername(),
            "role",     user.getRole().name(),
            "fullName", user.getFullName()
        ));
    }

    /** POST /api/v1/auth/register — creates a new user account */
    @PostMapping("/register")
    public ResponseEntity<Map<String, Object>> register(@RequestBody Map<String, String> body) {
        if (userRepository.existsByUsername(body.get("username"))) {
            return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(Map.of("error", "Username already exists"));
        }

        User user = User.builder()
            .username(body.get("username"))
            .email(body.get("email"))
            .password(passwordEncoder.encode(body.get("password")))
            .fullName(body.get("fullName"))
            .role(parseRole(body.getOrDefault("role", "NURSE")))
            .enabled(true)
            .build();

        userRepository.save(user);
        String token = jwtService.generateToken(user);

        return ResponseEntity.status(HttpStatus.CREATED).body(Map.of(
            "token",    token,
            "username", user.getUsername(),
            "role",     user.getRole().name()
        ));
    }

    private User.Role parseRole(String role) {
        try { return User.Role.valueOf(role.toUpperCase()); }
        catch (Exception e) { return User.Role.NURSE; }
    }
}
