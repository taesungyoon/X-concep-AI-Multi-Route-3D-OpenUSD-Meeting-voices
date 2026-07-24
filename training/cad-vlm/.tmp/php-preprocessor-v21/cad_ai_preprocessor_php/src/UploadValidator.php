<?php
declare(strict_types=1);

namespace CadAi;

final class UploadValidator
{
    private const ALLOWED_EXTENSIONS = ['dxf', 'step', 'stp'];

    public function __construct(private readonly int $maxBytes)
    {
    }

    public function validate(string $path, string $originalName): array
    {
        if (!is_file($path) || !is_readable($path)) {
            throw new ValidationException('upload_missing', '업로드 파일을 읽을 수 없습니다.');
        }
        $safeName = basename(str_replace('\\', '/', trim($originalName)));
        if ($safeName === '' || mb_strlen($safeName) > 255) {
            throw new ValidationException('invalid_filename', '파일명이 올바르지 않습니다.');
        }
        $extension = strtolower((string)pathinfo($safeName, PATHINFO_EXTENSION));
        if (!in_array($extension, self::ALLOWED_EXTENSIONS, true)) {
            throw new ValidationException('unsupported_extension', 'DXF, STEP, STP 파일만 허용합니다.');
        }
        $size = filesize($path);
        if ($size === false || $size < 1 || $size > $this->maxBytes) {
            throw new ValidationException('invalid_size', '파일 크기가 허용 범위를 벗어났습니다.');
        }
        $prefix = file_get_contents($path, false, null, 0, min(8192, $size));
        if ($prefix === false || str_contains($prefix, "\0")) {
            throw new ValidationException('binary_or_corrupt', '텍스트 기반 CAD 파일이 아닙니다.');
        }
        $format = $extension === 'dxf' ? 'dxf' : 'step';
        if ($format === 'dxf') {
            if (!self::hasDxfHeader($prefix)) {
                throw new ValidationException('invalid_signature', '유효한 ASCII DXF 헤더를 찾을 수 없습니다.');
            }
        } elseif (!str_contains(strtoupper($prefix), 'ISO-10303-21')) {
            throw new ValidationException('invalid_signature', '유효한 STEP Part21 헤더를 찾을 수 없습니다.');
        }

        return [
            'original_filename' => $safeName,
            'extension' => $extension,
            'source_format' => $format,
            'size_bytes' => $size,
            'sha256' => hash_file('sha256', $path),
        ];
    }

    private static function hasDxfHeader(string $prefix): bool
    {
        $lines = preg_split('/\R/', $prefix, 5);
        if (!is_array($lines) || count($lines) < 4) {
            return false;
        }
        $firstCode = ltrim(trim($lines[0]), "\xEF\xBB\xBF");
        return $firstCode === '0'
            && strtoupper(trim($lines[1])) === 'SECTION'
            && trim($lines[2]) === '2'
            && strtoupper(trim($lines[3])) === 'HEADER';
    }
}

final class ValidationException extends \RuntimeException
{
    public function __construct(public readonly string $errorCode, string $message)
    {
        parent::__construct($message);
    }
}
