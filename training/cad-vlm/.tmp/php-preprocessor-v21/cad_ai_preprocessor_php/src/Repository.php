<?php
declare(strict_types=1);

namespace CadAi;

use PDO;

final class Repository
{
    public function __construct(private readonly PDO $pdo)
    {
    }

    public function createJob(array $job): void
    {
        $sql = 'INSERT INTO jobs (
            id,status,stage,progress,original_filename,stored_filename,source_format,
            size_bytes,sha256,category,project_group,description,split_name,quality_score,
            package_path,error_code,error_message,warnings_json,created_at,updated_at
        ) VALUES (
            :id,:status,:stage,:progress,:original_filename,:stored_filename,:source_format,
            :size_bytes,:sha256,:category,:project_group,:description,:split_name,:quality_score,
            :package_path,:error_code,:error_message,:warnings_json,:created_at,:updated_at
        )';
        $this->pdo->prepare($sql)->execute($job);
    }

    public function updateJob(string $id, array $fields): void
    {
        if ($fields === []) {
            return;
        }
        $allowed = [
            'status', 'stage', 'progress', 'quality_score', 'package_path',
            'error_code', 'error_message', 'warnings_json', 'updated_at',
        ];
        $sets = [];
        $params = ['id' => $id];
        foreach ($fields as $key => $value) {
            if (!in_array($key, $allowed, true)) {
                throw new \InvalidArgumentException("허용되지 않은 필드: {$key}");
            }
            $sets[] = "{$key} = :{$key}";
            $params[$key] = $value;
        }
        $this->pdo->prepare('UPDATE jobs SET ' . implode(', ', $sets) . ' WHERE id = :id')->execute($params);
    }

    public function addArtifact(string $jobId, string $relativePath, string $mediaType, int $size, string $sha256): void
    {
        $sql = 'INSERT INTO artifacts(job_id,relative_path,media_type,size_bytes,sha256)
                VALUES(:job_id,:relative_path,:media_type,:size_bytes,:sha256)';
        $this->pdo->prepare($sql)->execute([
            'job_id' => $jobId,
            'relative_path' => str_replace('\\', '/', $relativePath),
            'media_type' => $mediaType,
            'size_bytes' => $size,
            'sha256' => $sha256,
        ]);
    }

    public function getJob(string $id): ?array
    {
        $statement = $this->pdo->prepare('SELECT * FROM jobs WHERE id = :id');
        $statement->execute(['id' => $id]);
        $job = $statement->fetch();
        if ($job === false) {
            return null;
        }
        $job = $this->hydrateJob($job);
        $artifactStatement = $this->pdo->prepare(
            'SELECT relative_path,media_type,size_bytes,sha256 FROM artifacts WHERE job_id = :id ORDER BY relative_path'
        );
        $artifactStatement->execute(['id' => $id]);
        $job['artifacts'] = $artifactStatement->fetchAll();
        return $job;
    }

    public function listJobs(int $limit = 100): array
    {
        $statement = $this->pdo->prepare('SELECT * FROM jobs ORDER BY created_at DESC LIMIT :limit');
        $statement->bindValue(':limit', max(1, min(1000, $limit)), PDO::PARAM_INT);
        $statement->execute();
        return array_map(fn(array $row): array => $this->hydrateJob($row), $statement->fetchAll());
    }

    public function completedJobs(): array
    {
        $statement = $this->pdo->query(
            "SELECT * FROM jobs WHERE status = 'completed' AND category <> 'unlabeled' ORDER BY created_at"
        );
        return array_map(fn(array $row): array => $this->hydrateJob($row), $statement->fetchAll());
    }

    public function findArtifact(string $jobId, string $relativePath): ?array
    {
        $statement = $this->pdo->prepare(
            'SELECT relative_path,media_type,size_bytes,sha256 FROM artifacts
             WHERE job_id = :job_id AND relative_path = :relative_path'
        );
        $statement->execute(['job_id' => $jobId, 'relative_path' => str_replace('\\', '/', $relativePath)]);
        $row = $statement->fetch();
        return $row === false ? null : $row;
    }

    public function createTrainingRun(array $run): void
    {
        $sql = 'INSERT INTO training_runs(
            id,status,algorithm,sample_count,class_count,model_path,metrics_json,error_message,created_at,updated_at
        ) VALUES(
            :id,:status,:algorithm,:sample_count,:class_count,:model_path,:metrics_json,:error_message,:created_at,:updated_at
        )';
        $this->pdo->prepare($sql)->execute($run);
    }

    public function listTrainingRuns(): array
    {
        return array_map(
            fn(array $row): array => $this->hydrateTraining($row),
            $this->pdo->query('SELECT * FROM training_runs ORDER BY created_at DESC')->fetchAll()
        );
    }

    public function getTrainingRun(string $id): ?array
    {
        $statement = $this->pdo->prepare('SELECT * FROM training_runs WHERE id = :id');
        $statement->execute(['id' => $id]);
        $row = $statement->fetch();
        return $row === false ? null : $this->hydrateTraining($row);
    }

    private function hydrateJob(array $job): array
    {
        $warningsJson = (string)($job['warnings_json'] ?? '[]');
        $job['progress'] = (int)$job['progress'];
        $job['size_bytes'] = (int)$job['size_bytes'];
        $job['quality_score'] = $job['quality_score'] === null ? null : (float)$job['quality_score'];
        $job['split'] = $job['split_name'];
        unset($job['split_name'], $job['warnings_json']);
        $job['warnings'] = json_decode($warningsJson, true) ?: [];
        return $job;
    }

    private function hydrateTraining(array $row): array
    {
        $row['sample_count'] = (int)$row['sample_count'];
        $row['class_count'] = (int)$row['class_count'];
        $row['metrics'] = json_decode((string)$row['metrics_json'], true) ?: [];
        unset($row['metrics_json']);
        return $row;
    }
}
