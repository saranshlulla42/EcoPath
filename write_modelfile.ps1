$modelfilePath = "C:\Capstone Project\EcoPath\ecopath\artifacts\exp_001\exported\Modelfile"
$modelfileContent = @"
FROM qwen2.5:7b-instruct

PARAMETER temperature 0.2
PARAMETER top_p 0.9
PARAMETER num_predict 700
PARAMETER stop "<|im_end|>"
PARAMETER stop "<|im_start|>"

SYSTEM You are a conservation science assistant drafting concise decision-support reports for human experts. Use only the provided species profile and evidence. Return JSON only.
"@

Set-Content -Encoding UTF8 -Path $modelfilePath -Value $modelfileContent
Write-Output "Wrote Modelfile to: $modelfilePath"