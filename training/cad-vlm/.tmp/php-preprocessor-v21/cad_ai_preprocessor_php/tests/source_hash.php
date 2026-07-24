<?php
declare(strict_types=1);

require dirname(__DIR__) . '/bootstrap.php';
require __DIR__ . '/ValidationSupport.php';

echo CadAi\Tests\ValidationSupport::sourceHash(dirname(__DIR__));
