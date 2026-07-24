<?php
declare(strict_types=1);

namespace CadAi\Tests;

use CadAi\BaselineTrainer;
use CadAi\Config;
use CadAi\Database;
use CadAi\DatasetPipeline;
use CadAi\Repository;
use CadAi\UploadValidator;
use CadAi\ValidationException;
use CadAi\Parsers\DxfParser;
use CadAi\Parsers\StepParser;
use ZipArchive;

final class Suite
{
    public function __construct(private readonly string $projectRoot)
    {
    }

    public function execute(string $workspace): array
    {
        $harness = new TestHarness();
        $dxfPath = $this->projectRoot . '/samples/simple.dxf';
        $stepPath = $this->projectRoot . '/samples/simple.step';
        $invalidPath = $this->projectRoot . '/samples/invalid.txt';

        $harness->run('DXF parser, validation and geometry contract', function () use (
            $harness, $workspace, $dxfPath, $invalidPath
        ): void {
            $data = (new DxfParser())->parse($dxfPath);
            $harness->assertSame('php_ascii_dxf_v1', $data['parser_mode'], 'DXF parser mode');
            $harness->assertTrue(($data['entity_counts']['LINE'] ?? 0) >= 1, 'LINE entity missing');
            $harness->assertTrue(($data['entity_counts']['CIRCLE'] ?? 0) >= 1, 'CIRCLE entity missing');
            $harness->assertTrue($data['bbox'] !== null, 'DXF bbox missing');
            $harness->assertTrue(count($data['layers']) >= 1, 'DXF layers missing');
            $validator = new UploadValidator(50 * 1024 * 1024);
            $longHeaderPath = $workspace . '/long_header.dxf';
            file_put_contents(
                $longHeaderPath,
                "  0\r\nSECTION\r\n  2\r\nHEADER\r\n"
                . str_repeat("  9\r\n\$COMMENT\r\n  1\r\nHEADER-PADDING\r\n", 300)
                . "  0\r\nENDSEC\r\n  0\r\nSECTION\r\n  2\r\nENTITIES\r\n"
                . "  0\r\nLINE\r\n  8\r\n0\r\n 10\r\n0\r\n 20\r\n0\r\n"
                . " 11\r\n1\r\n 21\r\n1\r\n  0\r\nENDSEC\r\n  0\r\nEOF\r\n"
            );
            $longHeader = $validator->validate($longHeaderPath, 'long_header.dxf');
            $harness->assertSame('dxf', $longHeader['source_format'], 'long-header DXF was rejected');
            $cp949Path = $workspace . '/cp949_text.dxf';
            $cp949Text = mb_convert_encoding('속도제어', 'CP949', 'UTF-8');
            file_put_contents(
                $cp949Path,
                "  0\r\nSECTION\r\n  2\r\nHEADER\r\n  9\r\n\$DWGCODEPAGE\r\n  3\r\nANSI_949\r\n"
                . "  0\r\nENDSEC\r\n  0\r\nSECTION\r\n  2\r\nENTITIES\r\n"
                . "  0\r\nTEXT\r\n  8\r\n문자\r\n 10\r\n0\r\n 20\r\n0\r\n  1\r\n"
                . $cp949Text . "\r\n  0\r\nENDSEC\r\n  0\r\nEOF\r\n"
            );
            $cp949Data = (new DxfParser())->parse($cp949Path);
            $harness->assertTrue(
                in_array('속도제어', $cp949Data['texts'], true),
                'CP949 DXF text was not converted to UTF-8'
            );
            $harness->assertThrows(
                ValidationException::class,
                static fn() => $validator->validate($invalidPath, 'invalid.txt'),
                'unsupported extension was accepted'
            );
        });

        $harness->run('STEP parser and topology contract', function () use ($harness, $stepPath): void {
            $data = (new StepParser())->parse($stepPath);
            $harness->assertSame('php_part21_step_v1', $data['parser_mode'], 'STEP parser mode');
            $harness->assertTrue(count($data['products']) >= 1, 'STEP product missing');
            $harness->assertTrue(count($data['points']) >= 2, 'STEP points missing');
            $harness->assertTrue($data['bbox'] !== null, 'STEP bbox missing');
            $harness->assertTrue(array_sum($data['entity_counts']) >= 1, 'STEP entities missing');
        });

        $context = null;
        $harness->run('Full dataset package pipeline', function () use (
            $harness, $workspace, $dxfPath, $stepPath, &$context
        ): void {
            $instance = $workspace . '/instance';
            $config = new Config(
                host: '127.0.0.1',
                port: 8080,
                instanceDir: $instance,
                maxUploadBytes: 50 * 1024 * 1024,
                apiKey: '',
                dsn: 'sqlite:' . $instance . '/cad_ai.sqlite3',
                dbUser: '',
                dbPassword: '',
            );
            $database = new Database($config);
            $repository = new Repository($database->pdo());
            $pipeline = new DatasetPipeline($config, $repository, new UploadValidator($config->maxUploadBytes));
            $dxfJob = $pipeline->ingest(
                $dxfPath, 'simple.dxf', 'bracket', 'validation-bracket', 'DXF validation sample'
            );
            $stepJob = $pipeline->ingest(
                $stepPath, 'simple.step', 'shaft', 'validation-shaft', 'STEP validation sample'
            );
            foreach ([$dxfJob, $stepJob] as $job) {
                $harness->assertSame('completed', $job['status'], 'job not completed');
                $harness->assertSame(100, $job['progress'], 'job progress');
                $harness->assertTrue((float)$job['quality_score'] >= 0.9, 'quality below gate');
                $harness->assertTrue(is_file($job['package_path']), 'package missing');
                $harness->assertTrue(count($job['artifacts']) === 10, 'artifact count mismatch');
                $zip = new ZipArchive();
                $harness->assertTrue($zip->open($job['package_path']) === true, 'package is not a ZIP');
                $harness->assertTrue($zip->locateName('manifest.json') !== false, 'manifest missing in ZIP');
                $harness->assertTrue($zip->locateName('geometry/geometry.json') !== false, 'geometry missing in ZIP');
                $zip->close();
            }
            $harness->assertSame(
                DatasetPipeline::splitForGroup('same-revision-group'),
                DatasetPipeline::splitForGroup('same-revision-group'),
                'group split must be deterministic'
            );
            $context = [$config, $repository, $dxfJob, $stepJob];
        });

        $harness->run('Baseline model training and prediction', function () use ($harness, &$context): void {
            $harness->assertTrue(is_array($context), 'pipeline context unavailable');
            [$config, $repository, $dxfJob] = $context;
            $trainer = new BaselineTrainer($config, $repository);
            $run = $trainer->train();
            $harness->assertSame('completed', $run['status'], 'training not completed');
            $harness->assertSame(2, $run['sample_count'], 'training sample count');
            $harness->assertSame(2, $run['class_count'], 'training class count');
            $harness->assertSame(
                'resubstitution_only_not_validation',
                $run['metrics']['evaluation_scope'],
                'evaluation scope'
            );
            $model = json_decode((string)file_get_contents($run['model_path']), true, flags: JSON_THROW_ON_ERROR);
            $vectorPath = $config->datasetDir() . '/' . $dxfJob['id'] . '/features/baseline_vector.json';
            $vector = json_decode((string)file_get_contents($vectorPath), true, flags: JSON_THROW_ON_ERROR)['vector'];
            $harness->assertSame('bracket', BaselineTrainer::predict($vector, $model), 'prediction mismatch');
        });

        return ['successful' => $harness->successful(), 'tests' => $harness->results()];
    }
}
