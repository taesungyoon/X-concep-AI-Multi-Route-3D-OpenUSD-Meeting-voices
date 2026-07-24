<?php
declare(strict_types=1);

namespace CadAi;

final class HttpApp
{
    private readonly Repository $repository;
    private readonly DatasetPipeline $pipeline;
    private readonly BaselineTrainer $trainer;

    public function __construct(private readonly Config $config)
    {
        $database = new Database($config);
        $this->repository = new Repository($database->pdo());
        $this->pipeline = new DatasetPipeline(
            $config,
            $this->repository,
            new UploadValidator($config->maxUploadBytes)
        );
        $this->trainer = new BaselineTrainer($config, $this->repository);
    }

    public function handle(): void
    {
        $requestId = bin2hex(random_bytes(16));
        $this->securityHeaders($requestId);
        try {
            $method = strtoupper($_SERVER['REQUEST_METHOD'] ?? 'GET');
            $path = rtrim((string)(parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH) ?: '/'), '/');
            $path = $path === '' ? '/' : $path;
            if (str_starts_with($path, '/api/')) {
                $this->authorize();
            }

            if ($method === 'GET' && $path === '/') {
                $this->serveFile(dirname(__DIR__) . '/public/index.html', 'text/html; charset=utf-8');
                return;
            }
            if ($method === 'GET' && $path === '/api/health') {
                $this->json(200, [
                    'status' => 'ok',
                    'version' => '1.0.0',
                    'runtime' => 'PHP ' . PHP_VERSION,
                    'queue_depth' => 0,
                ], $requestId);
                return;
            }
            if ($method === 'GET' && $path === '/api/jobs') {
                $limit = filter_input(INPUT_GET, 'limit', FILTER_VALIDATE_INT) ?: 100;
                $items = array_map($this->publicJob(...), $this->repository->listJobs($limit));
                $this->json(200, ['items' => $items], $requestId);
                return;
            }
            if ($method === 'POST' && $path === '/api/jobs') {
                $this->createJob($requestId);
                return;
            }
            if ($method === 'GET' && preg_match('#^/api/jobs/([A-Z0-9-]+)$#', $path, $match)) {
                $job = $this->repository->getJob($match[1]);
                if ($job === null) {
                    throw new HttpException(404, 'job_not_found', '작업을 찾을 수 없습니다.');
                }
                $this->json(200, $this->publicJob($job), $requestId);
                return;
            }
            if ($method === 'POST' && preg_match('#^/api/jobs/([A-Z0-9-]+)/retry$#', $path, $match)) {
                $job = $this->repository->getJob($match[1]);
                if ($job === null) {
                    throw new HttpException(404, 'job_not_found', '작업을 찾을 수 없습니다.');
                }
                $sourcePath = $this->config->sourceDir() . DIRECTORY_SEPARATOR . $job['stored_filename'];
                if (!is_file($sourcePath)) {
                    throw new HttpException(404, 'source_not_found', '재처리할 원본을 찾을 수 없습니다.');
                }
                $retried = $this->pipeline->ingest(
                    $sourcePath,
                    $job['original_filename'],
                    $job['category'],
                    $job['project_group'],
                    $job['description']
                );
                $this->json(202, ['job_id' => $retried['id'], 'status' => $retried['status']], $requestId);
                return;
            }
            if ($method === 'GET' && preg_match('#^/api/jobs/([A-Z0-9-]+)/artifact$#', $path, $match)) {
                $this->artifact($match[1]);
                return;
            }
            if ($method === 'GET' && preg_match('#^/api/jobs/([A-Z0-9-]+)/download$#', $path, $match)) {
                $this->download($match[1]);
                return;
            }
            if ($method === 'GET' && $path === '/api/datasets/manifest') {
                $this->manifest();
                return;
            }
            if ($method === 'GET' && $path === '/api/training/runs') {
                $items = array_map($this->publicTrainingRun(...), $this->repository->listTrainingRuns());
                $this->json(200, ['items' => $items], $requestId);
                return;
            }
            if ($method === 'POST' && $path === '/api/training/runs') {
                $run = $this->trainer->train();
                $this->json(202, ['run_id' => $run['id'], 'status' => $run['status']], $requestId);
                return;
            }
            if ($method === 'GET' && preg_match('#^/api/training/runs/([A-Z0-9-]+)$#', $path, $match)) {
                $run = $this->repository->getTrainingRun($match[1]);
                if ($run === null) {
                    throw new HttpException(404, 'training_not_found', '학습 실행을 찾을 수 없습니다.');
                }
                $this->json(200, $this->publicTrainingRun($run), $requestId);
                return;
            }
            throw new HttpException(404, 'not_found', 'API 경로를 찾을 수 없습니다.');
        } catch (ValidationException $exception) {
            $this->jsonError(422, $exception->errorCode, $exception->getMessage(), $requestId);
        } catch (HttpException $exception) {
            $this->jsonError($exception->status, $exception->errorCode, $exception->getMessage(), $requestId);
        } catch (\Throwable $exception) {
            error_log(json_encode([
                'level' => 'error',
                'request_id' => $requestId,
                'type' => $exception::class,
                'message' => $exception->getMessage(),
            ], JSON_UNESCAPED_UNICODE));
            $this->jsonError(500, 'internal_error', '요청을 처리하지 못했습니다.', $requestId);
        }
    }

    private function createJob(string $requestId): void
    {
        if (!isset($_FILES['file']) || !is_array($_FILES['file'])) {
            throw new ValidationException('file_required', 'CAD 파일이 필요합니다.');
        }
        $file = $_FILES['file'];
        if (($file['error'] ?? UPLOAD_ERR_NO_FILE) !== UPLOAD_ERR_OK) {
            throw new ValidationException('upload_failed', '파일 업로드에 실패했습니다.');
        }
        $job = $this->pipeline->ingest(
            (string)$file['tmp_name'],
            (string)$file['name'],
            (string)($_POST['category'] ?? 'unlabeled'),
            (string)($_POST['project_group'] ?? ''),
            (string)($_POST['description'] ?? '')
        );
        $this->json(202, ['job_id' => $job['id'], 'status' => $job['status']], $requestId);
    }

    private function artifact(string $jobId): void
    {
        $relative = str_replace('\\', '/', trim((string)($_GET['path'] ?? ''), '/'));
        if ($relative === '' || str_contains($relative, '..') || str_starts_with($relative, '/')) {
            throw new HttpException(400, 'invalid_artifact_path', '산출물 경로가 올바르지 않습니다.');
        }
        $artifact = $this->repository->findArtifact($jobId, $relative);
        if ($artifact === null) {
            throw new HttpException(404, 'artifact_not_found', '산출물을 찾을 수 없습니다.');
        }
        $base = realpath($this->config->datasetDir() . DIRECTORY_SEPARATOR . $jobId);
        $path = realpath($this->config->datasetDir() . DIRECTORY_SEPARATOR . $jobId
            . DIRECTORY_SEPARATOR . str_replace('/', DIRECTORY_SEPARATOR, $relative));
        if ($base === false || $path === false || !str_starts_with($path, $base . DIRECTORY_SEPARATOR)) {
            throw new HttpException(403, 'artifact_forbidden', '산출물 경로 접근이 거부되었습니다.');
        }
        $this->serveFile($path, $artifact['media_type'], basename($relative));
    }

    private function download(string $jobId): void
    {
        $job = $this->repository->getJob($jobId);
        if ($job === null || $job['status'] !== 'completed' || !is_file((string)$job['package_path'])) {
            throw new HttpException(404, 'package_not_found', '완료된 패키지를 찾을 수 없습니다.');
        }
        $this->serveFile((string)$job['package_path'], 'application/zip', $jobId . '.zip', true);
    }

    private function manifest(): void
    {
        header('Content-Type: application/x-ndjson; charset=utf-8');
        foreach ($this->repository->listJobs(1000) as $job) {
            if ($job['status'] !== 'completed') {
                continue;
            }
            $path = $this->config->datasetDir() . DIRECTORY_SEPARATOR . $job['id'] . DIRECTORY_SEPARATOR . 'manifest.jsonl';
            if (is_file($path)) {
                readfile($path);
            }
        }
    }

    private function authorize(): void
    {
        if ($this->config->apiKey === '') {
            return;
        }
        $provided = (string)($_SERVER['HTTP_X_API_KEY'] ?? '');
        if (!hash_equals($this->config->apiKey, $provided)) {
            throw new HttpException(401, 'unauthorized', 'API 인증에 실패했습니다.');
        }
    }

    private function json(int $status, array $data, string $requestId): void
    {
        http_response_code($status);
        header('Content-Type: application/json; charset=utf-8');
        echo json_encode([
            'ok' => true,
            'data' => $data,
            'error' => null,
            'meta' => ['request_id' => $requestId],
        ], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    }

    private function jsonError(int $status, string $code, string $message, string $requestId): void
    {
        http_response_code($status);
        header('Content-Type: application/json; charset=utf-8');
        echo json_encode([
            'ok' => false,
            'data' => null,
            'error' => ['code' => $code, 'message' => $message],
            'meta' => ['request_id' => $requestId],
        ], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    }

    private function serveFile(string $path, string $mediaType, ?string $name = null, bool $attachment = false): void
    {
        if (!is_file($path)) {
            throw new HttpException(404, 'file_not_found', '파일을 찾을 수 없습니다.');
        }
        header('Content-Type: ' . $mediaType);
        header('Content-Length: ' . filesize($path));
        if ($name !== null) {
            $mode = $attachment ? 'attachment' : 'inline';
            header("Content-Disposition: {$mode}; filename*=UTF-8''" . rawurlencode($name));
        }
        readfile($path);
    }

    private function securityHeaders(string $requestId): void
    {
        header_remove('X-Powered-By');
        header('X-Content-Type-Options: nosniff');
        header('X-Frame-Options: DENY');
        header('Referrer-Policy: no-referrer');
        header("Content-Security-Policy: default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; base-uri 'none'; frame-ancestors 'none'");
        header('X-Request-ID: ' . $requestId);
        header('Cache-Control: no-store');
    }

    private function publicJob(array $job): array
    {
        $job['package_available'] = $job['status'] === 'completed'
            && is_file((string)($job['package_path'] ?? ''));
        unset($job['package_path'], $job['stored_filename']);
        if ($job['status'] === 'failed') {
            $job['error_message'] = '전처리 작업에 실패했습니다.';
        }
        return $job;
    }

    private function publicTrainingRun(array $run): array
    {
        $run['model_available'] = $run['status'] === 'completed'
            && is_file((string)($run['model_path'] ?? ''));
        unset($run['model_path']);
        return $run;
    }
}

final class HttpException extends \RuntimeException
{
    public function __construct(
        public readonly int $status,
        public readonly string $errorCode,
        string $message,
    ) {
        parent::__construct($message);
    }
}
