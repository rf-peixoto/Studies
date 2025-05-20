<?php
declare(strict_types=1);

/**
 * Configuration
 */
$templates = [
    '/admin/config/',
    '/api/v2/users/{userId}/logs/',
    '/dashboard/{sessionId}/overview',
    '/settings/{userId}/preferences',
    '/search?q={query}&page={page}',
    '/data/{datasetId}/export',
    '/reports/{year}/{month}/summary',
];

$logFile = __DIR__ . '/rabbit_hole.log';

/**
 * Retrieve client IP address.
 */
function getClientIp(): string
{
    foreach (['HTTP_CLIENT_IP', 'HTTP_X_FORWARDED_FOR', 'REMOTE_ADDR'] as $key) {
        if (!empty($_SERVER[$key])) {
            $parts = explode(',', $_SERVER[$key]);
            return trim($parts[0]);
        }
    }
    return '0.0.0.0';
}

/**
 * Replace template variables with randomized but plausible values.
 */
function generateNextPath(array $templates): string
{
    $tpl = $templates[array_rand($templates)];
    return preg_replace_callback(
        '/\{(\w+)\}/',
        function (array $matches): string {
            switch ($matches[1]) {
                case 'userId':
                    return (string) random_int(1, 99999);
                case 'sessionId':
                    return (string) random_int(100000, 999999);
                case 'query':
                    $words = ['status','update','detail','info','check','view','conn'];
                    return $words[array_rand($words)];
                case 'page':
                    return (string) random_int(1, 999);
                case 'datasetId':
                    return bin2hex(random_bytes(8));
                case 'year':
                    return (string) random_int((int) date('Y') - 3, (int) date('Y'));
                case 'month':
                    return str_pad((string) random_int(1, 12), 2, '0', STR_PAD_LEFT);
                default:
                    // Unknown placeholder: leave as-is
                    return $matches[0];
            }
        },
        $tpl
    );
}

/**
 * Append an entry to the log file in JSON lines format.
 */
function logActivity(string $file, array $data): void
{
    $line = json_encode($data, JSON_UNESCAPED_SLASHES) . PHP_EOL;
    @file_put_contents($file, $line, FILE_APPEND | LOCK_EX);
}

/** Main execution **/

$clientIp   = getClientIp();
$userAgent  = $_SERVER['HTTP_USER_AGENT'] ?? 'unknown';
$requested  = $_SERVER['REQUEST_URI'] ?? '/';
$nextPath   = generateNextPath($templates);
$timestamp  = date('c');  // ISO 8601

// Log the interaction
logActivity($logFile, [
    'timestamp'       => $timestamp,
    'client_ip'       => $clientIp,
    'user_agent'      => $userAgent,
    'requested_uri'   => $requested,
    'generated_path'  => $nextPath,
]);

// Emit decoy page
http_response_code(200);
header('Content-Type: text/html; charset=UTF-8');
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Loading…</title>
</head>
<body>
    <p>Redirecting to <a href="<?= htmlspecialchars($nextPath, ENT_QUOTES, 'UTF-8') ?>"><?= htmlspecialchars($nextPath, ENT_QUOTES, 'UTF-8') ?></a></p>
    <script>
        // Auto-follow after short delay
        setTimeout(function(){
            window.location.href = "<?= addslashes($nextPath) ?>";
        }, 2000);
    </script>
</body>
</html>
