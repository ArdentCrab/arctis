$pipelineId = "pipe-1c2e6aa0-6578-47fa-ba78-468988b6fc52"
$apiKey = "ARCTIS_DEV_123"

1..10 | ForEach-Object {
    $i = $_
    $body = '{"input":{"x":"Hallo Welt"}}'
    $headers = @{ "x-api-key" = $apiKey }

    $result = Invoke-RestMethod `
        -Method POST `
        -Uri "http://127.0.0.1:8000/pipelines/$pipelineId/run" `
        -Headers $headers `
        -ContentType "application/json" `
        -Body $body

    Write-Host ("Run {0}:" -f $i)
    $result.output
}
