<?php
declare(strict_types=1);

namespace CadAi;

final class BaselineTrainer
{
    public function __construct(
        private readonly Config $config,
        private readonly Repository $repository,
    ) {
    }

    public function train(): array
    {
        $runId = 'TRAIN-' . strtoupper(bin2hex(random_bytes(6)));
        $now = gmdate(DATE_ATOM);
        $samples = [];
        foreach ($this->repository->completedJobs() as $job) {
            $path = $this->config->datasetDir() . DIRECTORY_SEPARATOR . $job['id']
                . DIRECTORY_SEPARATOR . 'features' . DIRECTORY_SEPARATOR . 'baseline_vector.json';
            $payload = is_file($path) ? json_decode((string)file_get_contents($path), true) : null;
            if (is_array($payload['vector'] ?? null)) {
                $samples[] = ['label' => $job['category'], 'vector' => array_map('floatval', $payload['vector'])];
            }
        }
        $labels = array_values(array_unique(array_column($samples, 'label')));
        if (count($samples) < 2 || count($labels) < 2) {
            throw new ValidationException('insufficient_training_data', '2개 이상의 클래스와 완료 샘플이 필요합니다.');
        }
        $dimension = count($samples[0]['vector']);
        $means = array_fill(0, $dimension, 0.0);
        $stds = array_fill(0, $dimension, 0.0);
        foreach ($samples as $sample) {
            foreach ($sample['vector'] as $i => $value) {
                $means[$i] += $value;
            }
        }
        foreach ($means as $i => $value) {
            $means[$i] = $value / count($samples);
        }
        foreach ($samples as $sample) {
            foreach ($sample['vector'] as $i => $value) {
                $stds[$i] += ($value - $means[$i]) ** 2;
            }
        }
        foreach ($stds as $i => $value) {
            $stds[$i] = max(sqrt($value / count($samples)), 1.0e-9);
        }
        $normalized = array_map(
            fn(array $sample): array => [
                'label' => $sample['label'],
                'vector' => $this->normalize($sample['vector'], $means, $stds),
            ],
            $samples
        );
        $centroids = [];
        foreach ($labels as $label) {
            $members = array_values(array_filter($normalized, fn(array $sample): bool => $sample['label'] === $label));
            $centroid = array_fill(0, $dimension, 0.0);
            foreach ($members as $member) {
                foreach ($member['vector'] as $i => $value) {
                    $centroid[$i] += $value;
                }
            }
            foreach ($centroid as $i => $value) {
                $centroid[$i] = $value / count($members);
            }
            $centroids[$label] = $centroid;
        }
        $correct = 0;
        $matrix = [];
        foreach ($labels as $actual) {
            $matrix[$actual] = array_fill_keys($labels, 0);
        }
        foreach ($normalized as $sample) {
            $predicted = self::predictNormalized($sample['vector'], $centroids);
            $matrix[$sample['label']][$predicted]++;
            $correct += (int)($predicted === $sample['label']);
        }
        $metrics = [
            'training_accuracy' => $correct / count($samples),
            'confusion_matrix' => $matrix,
            'evaluation_scope' => 'resubstitution_only_not_validation',
        ];
        $model = [
            'schema_version' => '1.0',
            'algorithm' => 'nearest_centroid_php_v1',
            'means' => $means,
            'stds' => $stds,
            'centroids' => $centroids,
            'metrics' => $metrics,
        ];
        $modelPath = $this->config->modelDir() . DIRECTORY_SEPARATOR . $runId . '.json';
        ArtifactWriter::writeJson($modelPath, $model);
        $this->repository->createTrainingRun([
            'id' => $runId,
            'status' => 'completed',
            'algorithm' => 'nearest_centroid_php_v1',
            'sample_count' => count($samples),
            'class_count' => count($labels),
            'model_path' => $modelPath,
            'metrics_json' => json_encode($metrics, JSON_UNESCAPED_UNICODE),
            'error_message' => null,
            'created_at' => $now,
            'updated_at' => gmdate(DATE_ATOM),
        ]);
        return $this->repository->getTrainingRun($runId) ?? throw new \RuntimeException('학습 결과 조회 실패');
    }

    public static function predict(array $vector, array $model): string
    {
        $normalized = [];
        foreach ($vector as $i => $value) {
            $normalized[] = ((float)$value - (float)$model['means'][$i]) / (float)$model['stds'][$i];
        }
        return self::predictNormalized($normalized, $model['centroids']);
    }

    private function normalize(array $vector, array $means, array $stds): array
    {
        return array_map(
            static fn(float $value, int $i): float => ($value - $means[$i]) / $stds[$i],
            $vector,
            array_keys($vector)
        );
    }

    private static function predictNormalized(array $vector, array $centroids): string
    {
        $bestLabel = '';
        $bestDistance = INF;
        foreach ($centroids as $label => $centroid) {
            $distance = 0.0;
            foreach ($vector as $i => $value) {
                $distance += ($value - $centroid[$i]) ** 2;
            }
            if ($distance < $bestDistance) {
                $bestDistance = $distance;
                $bestLabel = $label;
            }
        }
        return $bestLabel;
    }
}
