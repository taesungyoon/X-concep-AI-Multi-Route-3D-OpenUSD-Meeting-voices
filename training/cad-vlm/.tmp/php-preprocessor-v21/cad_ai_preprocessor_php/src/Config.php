<?php
declare(strict_types=1);

namespace CadAi;

use InvalidArgumentException;

final readonly class Config
{
    public function __construct(
        public string $host,
        public int $port,
        public string $instanceDir,
        public int $maxUploadBytes,
        public string $apiKey,
        public string $dsn,
        public string $dbUser,
        public string $dbPassword,
    ) {
    }

    public static function fromEnvironment(?string $projectRoot = null): self
    {
        $root = $projectRoot ?? dirname(__DIR__);
        $instance = self::env('CAD_AI_INSTANCE', $root . DIRECTORY_SEPARATOR . 'instance');
        if (!self::isAbsolutePath($instance)) {
            $instance = $root . DIRECTORY_SEPARATOR . $instance;
        }
        $instance = self::normalizePath($instance);
        $maxMb = self::boundedInt('CAD_AI_MAX_UPLOAD_MB', 50, 1, 2048);
        $port = self::boundedInt('CAD_AI_PORT', 8080, 1, 65535);
        $dsn = self::env('CAD_AI_DSN', 'sqlite:' . $instance . DIRECTORY_SEPARATOR . 'cad_ai.sqlite3');

        return new self(
            host: self::env('CAD_AI_HOST', '127.0.0.1'),
            port: $port,
            instanceDir: $instance,
            maxUploadBytes: $maxMb * 1024 * 1024,
            apiKey: self::env('CAD_AI_API_KEY', ''),
            dsn: $dsn,
            dbUser: self::env('CAD_AI_DB_USER', ''),
            dbPassword: self::env('CAD_AI_DB_PASSWORD', ''),
        );
    }

    public function ensureDirectories(): void
    {
        foreach ([$this->instanceDir, $this->sourceDir(), $this->datasetDir(), $this->packageDir(), $this->modelDir()] as $dir) {
            if (!is_dir($dir) && !mkdir($dir, 0770, true) && !is_dir($dir)) {
                throw new \RuntimeException("디렉터리를 생성할 수 없습니다: {$dir}");
            }
        }
    }

    public function sourceDir(): string { return $this->instanceDir . DIRECTORY_SEPARATOR . 'source'; }
    public function datasetDir(): string { return $this->instanceDir . DIRECTORY_SEPARATOR . 'dataset'; }
    public function packageDir(): string { return $this->instanceDir . DIRECTORY_SEPARATOR . 'packages'; }
    public function modelDir(): string { return $this->instanceDir . DIRECTORY_SEPARATOR . 'models'; }

    private static function env(string $name, string $default): string
    {
        $value = getenv($name);
        return $value === false || $value === '' ? $default : $value;
    }

    private static function boundedInt(string $name, int $default, int $min, int $max): int
    {
        $raw = self::env($name, (string)$default);
        if (filter_var($raw, FILTER_VALIDATE_INT) === false) {
            throw new InvalidArgumentException("{$name}은 정수여야 합니다.");
        }
        $value = (int)$raw;
        if ($value < $min || $value > $max) {
            throw new InvalidArgumentException("{$name}은 {$min}~{$max} 범위여야 합니다.");
        }
        return $value;
    }

    private static function isAbsolutePath(string $path): bool
    {
        return preg_match('/^[A-Za-z]:[\\\\\\/]/', $path) === 1 || str_starts_with($path, DIRECTORY_SEPARATOR);
    }

    private static function normalizePath(string $path): string
    {
        $path = str_replace(['/', '\\'], DIRECTORY_SEPARATOR, $path);
        $parts = [];
        $prefix = '';
        if (preg_match('/^[A-Za-z]:/', $path, $match) === 1) {
            $prefix = $match[0] . DIRECTORY_SEPARATOR;
            $path = substr($path, 2);
        } elseif (str_starts_with($path, DIRECTORY_SEPARATOR)) {
            $prefix = DIRECTORY_SEPARATOR;
        }
        foreach (explode(DIRECTORY_SEPARATOR, trim($path, DIRECTORY_SEPARATOR)) as $part) {
            if ($part === '' || $part === '.') {
                continue;
            }
            if ($part === '..') {
                array_pop($parts);
                continue;
            }
            $parts[] = $part;
        }
        return $prefix . implode(DIRECTORY_SEPARATOR, $parts);
    }
}
