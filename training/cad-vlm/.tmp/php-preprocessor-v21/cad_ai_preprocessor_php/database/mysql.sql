CREATE TABLE jobs (
    id VARCHAR(32) PRIMARY KEY,
    status VARCHAR(24) NOT NULL,
    stage VARCHAR(32) NOT NULL,
    progress INT NOT NULL DEFAULT 0,
    original_filename VARCHAR(255) NOT NULL,
    stored_filename VARCHAR(255) NOT NULL,
    source_format VARCHAR(12) NOT NULL,
    size_bytes BIGINT NOT NULL,
    sha256 CHAR(64) NOT NULL,
    category VARCHAR(120) NOT NULL,
    project_group VARCHAR(180) NOT NULL,
    description LONGTEXT NOT NULL,
    split_name VARCHAR(16) NOT NULL,
    quality_score DOUBLE NULL,
    package_path LONGTEXT NULL,
    error_code VARCHAR(80) NULL,
    error_message LONGTEXT NULL,
    warnings_json LONGTEXT NOT NULL,
    created_at VARCHAR(40) NOT NULL,
    updated_at VARCHAR(40) NOT NULL,
    INDEX idx_jobs_created (created_at),
    INDEX idx_jobs_sha (sha256)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE artifacts (
    artifact_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    job_id VARCHAR(32) NOT NULL,
    relative_path VARCHAR(500) NOT NULL,
    media_type VARCHAR(120) NOT NULL,
    size_bytes BIGINT NOT NULL,
    sha256 CHAR(64) NOT NULL,
    UNIQUE KEY uq_artifact_job_path (job_id, relative_path),
    CONSTRAINT fk_artifact_job FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE training_runs (
    id VARCHAR(40) PRIMARY KEY,
    status VARCHAR(24) NOT NULL,
    algorithm VARCHAR(80) NOT NULL,
    sample_count INT NOT NULL DEFAULT 0,
    class_count INT NOT NULL DEFAULT 0,
    model_path LONGTEXT NULL,
    metrics_json LONGTEXT NOT NULL,
    error_message LONGTEXT NULL,
    created_at VARCHAR(40) NOT NULL,
    updated_at VARCHAR(40) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
