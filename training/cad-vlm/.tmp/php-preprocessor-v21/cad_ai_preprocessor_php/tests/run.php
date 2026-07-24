<?php
declare(strict_types=1);

require dirname(__DIR__) . '/bootstrap.php';
require __DIR__ . '/TestHarness.php';
require __DIR__ . '/Suite.php';

use CadAi\Tests\Suite;

$root = dirname(__DIR__);
$workspace = sys_get_temp_dir() . '/cad_ai_php_test_' . bin2hex(random_bytes(6));
mkdir($workspace, 0770, true);
$result = (new Suite($root))->execute($workspace);
foreach ($result['tests'] as $test) {
    printf("%s %s (%.3f ms)%s\n",
        $test['successful'] ? 'PASS' : 'FAIL',
        $test['name'],
        $test['duration_ms'],
        $test['error'] ? ' - ' . $test['error'] : ''
    );
}
exit($result['successful'] ? 0 : 1);
