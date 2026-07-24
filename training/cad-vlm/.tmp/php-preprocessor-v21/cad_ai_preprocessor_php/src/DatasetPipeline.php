<?php
declare(strict_types=1);

namespace CadAi;

use CadAi\Parsers\DxfParser;
use CadAi\Parsers\StepParser;
use ZipArchive;

final class DatasetPipeline
{
    public function __construct(
        private readonly Config $config,
        private readonly Repository $repository,
        private readonly UploadValidator $validator,
        private readonly DxfParser $dxfParser = new DxfParser(),
        private readonly StepParser $stepParser = new StepParser(),
    ) {
    }

    public function ingest(
        string $uploadPath,
        string $originalName,
        string $category = 'unlabeled',
        string $projectGroup = '',
        string $description = '',
    ): array {
        $metadata = $this->validator->validate($uploadPath, $originalName);
        $jobId = 'CAD-' . strtoupper(bin2hex(random_bytes(6)));
        $storedFilename = bin2hex(random_bytes(16)) . '.' . $metadata['extension'];
        $category = $this->clean($category, 120, 'unlabeled');
        $projectGroup = $this->clean($projectGroup, 180, $metadata['sha256']);
        $description = $this->clean($description, 2000, '');
        $split = self::splitForGroup($projectGroup);
        $now = gmdate(DATE_ATOM);
        $job = [
            'id' => $jobId,
            'status' => 'queued',
            'stage' => 'queued',
            'progress' => 0,
            'original_filename' => $metadata['original_filename'],
            'stored_filename' => $storedFilename,
            'source_format' => $metadata['source_format'],
            'size_bytes' => $metadata['size_bytes'],
            'sha256' => $metadata['sha256'],
            'category' => $category,
            'project_group' => $projectGroup,
            'description' => $description,
            'split_name' => $split,
            'quality_score' => null,
            'package_path' => null,
            'error_code' => null,
            'error_message' => null,
            'warnings_json' => '[]',
            'created_at' => $now,
            'updated_at' => $now,
        ];
        $this->repository->createJob($job);

        try {
            $this->stage($jobId, 'validating', 10);
            $sourcePath = $this->config->sourceDir() . DIRECTORY_SEPARATOR . $storedFilename;
            if (!copy($uploadPath, $sourcePath)) {
                throw new \RuntimeException('원본 파일 저장에 실패했습니다.');
            }
            $this->stage($jobId, 'parsing', 25);
            $parsed = $metadata['source_format'] === 'dxf'
                ? $this->dxfParser->parse($sourcePath)
                : $this->stepParser->parse($sourcePath);

            $this->stage($jobId, 'normalizing', 45);
            $geometry = $this->geometryDocument($jobId, $metadata, $parsed);
            $jobDir = $this->config->datasetDir() . DIRECTORY_SEPARATOR . $jobId;
            $paths = $this->writeArtifacts(
                $jobDir,
                $sourcePath,
                $metadata['extension'],
                $geometry,
                $job,
                $category,
                $projectGroup,
                $description,
                $split
            );

            $this->stage($jobId, 'quality_check', 75);
            [$quality, $warnings] = $this->quality($geometry, $category, $description);
            ArtifactWriter::writeJson($paths['quality/report.json'], [
                'schema_version' => '1.0',
                'sample_id' => $jobId,
                'score' => $quality,
                'warnings' => $warnings,
                'checks' => [
                    'signature_valid' => true,
                    'parser_completed' => true,
                    'geometry_non_empty' => array_sum($parsed['entity_counts'] ?? []) > 0,
                    'bbox_available' => $parsed['bbox'] !== null,
                    'label_available' => $category !== 'unlabeled',
                ],
            ]);
            $this->stage($jobId, 'packaging', 88);
            $manifest = $this->manifest(
                $jobId, $metadata, $category, $projectGroup, $description,
                $split, $quality, $warnings, array_keys($paths)
            );
            ArtifactWriter::writeJson($paths['manifest.json'], $manifest);
            ArtifactWriter::writeText(
                $paths['manifest.jsonl'],
                json_encode($manifest, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES) . PHP_EOL
            );
            $packagePath = $this->config->packageDir() . DIRECTORY_SEPARATOR . $jobId . '.zip';
            $this->createZip($jobDir, $packagePath);
            $this->registerArtifacts($jobId, $jobDir);
            $this->repository->updateJob($jobId, [
                'status' => 'completed',
                'stage' => 'completed',
                'progress' => 100,
                'quality_score' => $quality,
                'package_path' => $packagePath,
                'warnings_json' => json_encode($warnings, JSON_UNESCAPED_UNICODE),
                'updated_at' => gmdate(DATE_ATOM),
            ]);
        } catch (\Throwable $exception) {
            $code = $exception instanceof ValidationException ? $exception->errorCode : 'pipeline_failed';
            $this->repository->updateJob($jobId, [
                'status' => 'failed',
                'stage' => 'failed',
                'progress' => 100,
                'error_code' => $code,
                'error_message' => $exception->getMessage(),
                'updated_at' => gmdate(DATE_ATOM),
            ]);
            throw $exception;
        }
        return $this->repository->getJob($jobId) ?? throw new \RuntimeException('작업 조회 실패');
    }

    public static function splitForGroup(string $group): string
    {
        $bucket = hexdec(substr(hash('sha256', $group), 0, 8)) % 100;
        return $bucket < 80 ? 'train' : ($bucket < 90 ? 'validation' : 'test');
    }

    private function stage(string $jobId, string $stage, int $progress): void
    {
        $this->repository->updateJob($jobId, [
            'status' => 'processing',
            'stage' => $stage,
            'progress' => $progress,
            'updated_at' => gmdate(DATE_ATOM),
        ]);
    }

    private function geometryDocument(string $jobId, array $metadata, array $parsed): array
    {
        $bbox = $parsed['bbox'];
        $center = $bbox === null ? [0.0, 0.0, 0.0] : [
            ($bbox['min'][0] + $bbox['max'][0]) / 2,
            ($bbox['min'][1] + $bbox['max'][1]) / 2,
            ($bbox['min'][2] + $bbox['max'][2]) / 2,
        ];
        $scale = $bbox === null ? 1.0 : max(1.0, ...array_map('abs', $bbox['extent']));
        return [
            'schema_version' => '1.0',
            'sample_id' => $jobId,
            'source' => [
                'format' => $metadata['source_format'],
                'original_filename' => $metadata['original_filename'],
                'sha256' => $metadata['sha256'],
                'size_bytes' => $metadata['size_bytes'],
            ],
            'parser_mode' => $parsed['parser_mode'],
            'entity_counts' => $parsed['entity_counts'] ?? [],
            'layers' => $parsed['layers'] ?? [],
            'texts' => $parsed['texts'] ?? [],
            'products' => $parsed['products'] ?? [],
            'points' => $parsed['points'] ?? [],
            'primitives' => $parsed['primitives'] ?? [],
            'bbox' => $bbox,
            'topology' => $parsed['topology'] ?? [],
            'surfaces' => $parsed['surfaces'] ?? [],
            'normalization' => ['center' => $center, 'scale' => $scale, 'units' => 'unknown'],
            'provenance' => ['implementation' => 'php', 'version' => '1.0.0', 'created_at' => gmdate(DATE_ATOM)],
        ];
    }

    private function writeArtifacts(
        string $jobDir,
        string $sourcePath,
        string $extension,
        array $geometry,
        array $job,
        string $category,
        string $projectGroup,
        string $description,
        string $split,
    ): array {
        $relative = [
            "source/original.{$extension}",
            'geometry/geometry.json',
            'images/preview.svg',
            'pointcloud/points_256.ply',
            'features/baseline_vector.json',
            'metadata/metadata.json',
            'metadata/label.json',
            'quality/report.json',
            'manifest.json',
            'manifest.jsonl',
        ];
        $paths = [];
        foreach ($relative as $item) {
            $paths[$item] = $jobDir . DIRECTORY_SEPARATOR . str_replace('/', DIRECTORY_SEPARATOR, $item);
        }
        foreach ($paths as $path) {
            $parent = dirname($path);
            if (!is_dir($parent)) {
                mkdir($parent, 0770, true);
            }
        }
        copy($sourcePath, $paths["source/original.{$extension}"]);
        ArtifactWriter::writeJson($paths['geometry/geometry.json'], $geometry);
        ArtifactWriter::writeText($paths['images/preview.svg'], ArtifactWriter::svg($geometry));
        ArtifactWriter::writeText($paths['pointcloud/points_256.ply'], ArtifactWriter::ply($geometry));
        ArtifactWriter::writeJson($paths['features/baseline_vector.json'], [
            'schema_version' => '1.0',
            'sample_id' => $job['id'],
            'vector' => ArtifactWriter::baselineVector($geometry),
        ]);
        ArtifactWriter::writeJson($paths['metadata/metadata.json'], [
            'sample_id' => $job['id'], 'source_format' => $job['source_format'],
            'sha256' => $job['sha256'], 'split' => $split,
        ]);
        ArtifactWriter::writeJson($paths['metadata/label.json'], [
            'sample_id' => $job['id'], 'category' => $category,
            'project_group' => $projectGroup, 'description' => $description,
            'inferred' => false,
        ]);
        return $paths;
    }

    private function quality(array $geometry, string $category, string $description): array
    {
        $score = 1.0;
        $warnings = [];
        if (array_sum($geometry['entity_counts'] ?? []) === 0) {
            $score -= 0.35;
            $warnings[] = 'geometry_empty';
        }
        if ($geometry['bbox'] === null) {
            $score -= 0.2;
            $warnings[] = 'bbox_missing';
        }
        if ($category === 'unlabeled') {
            $score -= 0.1;
            $warnings[] = 'label_missing';
        }
        if ($description === '') {
            $score -= 0.03;
            $warnings[] = 'description_missing';
        }
        return [round(max(0.0, $score), 4), $warnings];
    }

    private function manifest(
        string $jobId, array $metadata, string $category, string $group,
        string $description, string $split, float $quality, array $warnings, array $artifacts
    ): array {
        return [
            'schema_version' => '1.0',
            'sample_id' => $jobId,
            'source' => [
                'format' => $metadata['source_format'],
                'original_filename' => $metadata['original_filename'],
                'sha256' => $metadata['sha256'],
                'size_bytes' => $metadata['size_bytes'],
            ],
            'label' => ['category' => $category, 'project_group' => $group, 'description' => $description],
            'split' => $split,
            'quality' => ['score' => $quality, 'warnings' => $warnings],
            'artifacts' => array_values($artifacts),
            'provenance' => ['pipeline' => 'cad-ai-php', 'version' => '1.0.0', 'created_at' => gmdate(DATE_ATOM)],
        ];
    }

    private function createZip(string $jobDir, string $packagePath): void
    {
        $zip = new ZipArchive();
        if ($zip->open($packagePath, ZipArchive::CREATE | ZipArchive::OVERWRITE) !== true) {
            throw new \RuntimeException('ZIP 패키지를 생성할 수 없습니다.');
        }
        $iterator = new \RecursiveIteratorIterator(
            new \RecursiveDirectoryIterator($jobDir, \FilesystemIterator::SKIP_DOTS)
        );
        foreach ($iterator as $file) {
            if ($file->isFile()) {
                $relative = str_replace('\\', '/', substr($file->getPathname(), strlen($jobDir) + 1));
                $zip->addFile($file->getPathname(), $relative);
            }
        }
        $zip->close();
    }

    private function registerArtifacts(string $jobId, string $jobDir): void
    {
        $iterator = new \RecursiveIteratorIterator(
            new \RecursiveDirectoryIterator($jobDir, \FilesystemIterator::SKIP_DOTS)
        );
        foreach ($iterator as $file) {
            if (!$file->isFile()) {
                continue;
            }
            $relative = str_replace('\\', '/', substr($file->getPathname(), strlen($jobDir) + 1));
            $this->repository->addArtifact(
                $jobId,
                $relative,
                $this->mediaType($relative),
                $file->getSize(),
                hash_file('sha256', $file->getPathname())
            );
        }
    }

    private function mediaType(string $path): string
    {
        return match (strtolower(pathinfo($path, PATHINFO_EXTENSION))) {
            'json', 'jsonl' => 'application/json',
            'svg' => 'image/svg+xml',
            'ply' => 'application/octet-stream',
            'dxf', 'step', 'stp' => 'text/plain',
            default => 'application/octet-stream',
        };
    }

    private function clean(string $value, int $maxLength, string $default): string
    {
        $value = trim(preg_replace('/[\x00-\x1F\x7F]/u', '', $value) ?? '');
        if ($value === '') {
            return $default;
        }
        return mb_substr($value, 0, $maxLength);
    }
}
