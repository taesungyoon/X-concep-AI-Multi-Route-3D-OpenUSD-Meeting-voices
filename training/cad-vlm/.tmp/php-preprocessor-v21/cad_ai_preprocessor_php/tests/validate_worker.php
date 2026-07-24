<?php
declare(strict_types=1);

require dirname(__DIR__) . '/bootstrap.php';
require __DIR__ . '/TestHarness.php';
require __DIR__ . '/Suite.php';
require __DIR__ . '/ValidationSupport.php';

use CadAi\Tests\Suite;
use CadAi\Tests\ValidationSupport;

[$script, $workerId, $startCycle, $cycleCount, $reportDir, $workRoot] = $argv + array_fill(0, 6, '');
$workerId = (int)$workerId;
$startCycle = (int)$startCycle;
$cycleCount = (int)$cycleCount;
if ($workerId < 1 || $startCycle < 1 || $cycleCount < 1) {
    fwrite(STDERR, "invalid worker arguments\n");
    exit(2);
}
$root = dirname(__DIR__);
$suite = new Suite($root);
$durations = [];
$failedCycles = [];
$totalTests = 0;
$started = hrtime(true);
$progressPath = $reportDir . '/worker_' . $workerId . '_progress.json';

for ($index = 0; $index < $cycleCount; $index++) {
    $cycle = $startCycle + $index;
    $workspace = $workRoot . '/worker_' . $workerId . '_cycle_' . str_pad((string)$cycle, 5, '0', STR_PAD_LEFT);
    @mkdir($workspace, 0770, true);
    $cycleStart = hrtime(true);
    $result = $suite->execute($workspace);
    $durations[] = (hrtime(true) - $cycleStart) / 1_000_000_000;
    $totalTests += count($result['tests']);
    if (!$result['successful']) {
        $failedCycles[] = ['cycle' => $cycle, 'tests' => $result['tests']];
    }
    ValidationSupport::removeTree($workspace, $workRoot);
    $completed = $index + 1;
    if ($completed % 25 === 0 || $completed === $cycleCount) {
        file_put_contents($progressPath, json_encode([
            'worker_id' => $workerId,
            'completed_cycles' => $completed,
            'assigned_cycles' => $cycleCount,
            'failed_cycles' => count($failedCycles),
            'total_tests' => $totalTests,
        ], JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT), LOCK_EX);
    }
}

sort($durations);
$result = [
    'worker_id' => $workerId,
    'start_cycle' => $startCycle,
    'cycle_count' => $cycleCount,
    'successful_cycles' => $cycleCount - count($failedCycles),
    'failed_cycles' => count($failedCycles),
    'total_tests' => $totalTests,
    'duration_seconds' => round((hrtime(true) - $started) / 1_000_000_000, 3),
    'cycle_durations' => $durations,
    'failed_cycle_details' => $failedCycles,
];
file_put_contents(
    $reportDir . '/worker_' . $workerId . '_result.json',
    json_encode($result, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT) . PHP_EOL,
    LOCK_EX
);
exit($failedCycles === [] ? 0 : 1);
