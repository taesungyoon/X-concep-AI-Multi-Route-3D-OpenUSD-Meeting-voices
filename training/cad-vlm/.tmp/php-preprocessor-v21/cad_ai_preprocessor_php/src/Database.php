<?php
declare(strict_types=1);

namespace CadAi;

use PDO;

final class Database
{
    private PDO $pdo;

    public function __construct(private readonly Config $config)
    {
        $config->ensureDirectories();
        $this->pdo = new PDO(
            $config->dsn,
            $config->dbUser,
            $config->dbPassword,
            [
                PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
                PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
                PDO::ATTR_EMULATE_PREPARES => false,
            ]
        );
        if (str_starts_with($config->dsn, 'sqlite:')) {
            $this->pdo->exec('PRAGMA foreign_keys = ON');
            $this->pdo->exec('PRAGMA busy_timeout = 5000');
            $this->pdo->exec('PRAGMA journal_mode = WAL');
        }
        $this->migrate();
    }

    public function pdo(): PDO
    {
        return $this->pdo;
    }

    private function migrate(): void
    {
        $isMysql = str_starts_with($this->config->dsn, 'mysql:');
        $autoId = $isMysql ? 'BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY' : 'INTEGER PRIMARY KEY AUTOINCREMENT';
        $real = $isMysql ? 'DOUBLE' : 'REAL';
        $text = $isMysql ? 'LONGTEXT' : 'TEXT';
        $timestamp = $isMysql ? 'VARCHAR(40)' : 'TEXT';
        $jobIndexes = $isMysql
            ? ', INDEX idx_jobs_created (created_at), INDEX idx_jobs_sha (sha256)'
            : '';

        $this->pdo->exec(
            "CREATE TABLE IF NOT EXISTS jobs (
                id VARCHAR(32) PRIMARY KEY,
                status VARCHAR(24) NOT NULL,
                stage VARCHAR(32) NOT NULL,
                progress INTEGER NOT NULL DEFAULT 0,
                original_filename VARCHAR(255) NOT NULL,
                stored_filename VARCHAR(255) NOT NULL,
                source_format VARCHAR(12) NOT NULL,
                size_bytes BIGINT NOT NULL,
                sha256 CHAR(64) NOT NULL,
                category VARCHAR(120) NOT NULL,
                project_group VARCHAR(180) NOT NULL,
                description {$text} NOT NULL,
                split_name VARCHAR(16) NOT NULL,
                quality_score {$real} NULL,
                package_path {$text} NULL,
                error_code VARCHAR(80) NULL,
                error_message {$text} NULL,
                warnings_json {$text} NOT NULL,
                created_at {$timestamp} NOT NULL,
                updated_at {$timestamp} NOT NULL
                {$jobIndexes}
            )"
        );
        if (!$isMysql) {
            $this->pdo->exec('CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at)');
            $this->pdo->exec('CREATE INDEX IF NOT EXISTS idx_jobs_sha ON jobs(sha256)');
        }
        $this->pdo->exec(
            "CREATE TABLE IF NOT EXISTS artifacts (
                artifact_id {$autoId},
                job_id VARCHAR(32) NOT NULL,
                relative_path VARCHAR(500) NOT NULL,
                media_type VARCHAR(120) NOT NULL,
                size_bytes BIGINT NOT NULL,
                sha256 CHAR(64) NOT NULL,
                UNIQUE(job_id, relative_path),
                FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
            )"
        );
        $this->pdo->exec(
            "CREATE TABLE IF NOT EXISTS training_runs (
                id VARCHAR(40) PRIMARY KEY,
                status VARCHAR(24) NOT NULL,
                algorithm VARCHAR(80) NOT NULL,
                sample_count INTEGER NOT NULL DEFAULT 0,
                class_count INTEGER NOT NULL DEFAULT 0,
                model_path {$text} NULL,
                metrics_json {$text} NOT NULL,
                error_message {$text} NULL,
                created_at {$timestamp} NOT NULL,
                updated_at {$timestamp} NOT NULL
            )"
        );
    }
}
