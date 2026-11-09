Add-Type -AssemblyName System.Windows.Forms
for ($try = 0; $try -lt 20; $try++) {
  try {
    $image = [System.Windows.Forms.Clipboard]::GetImage()
    if ($image) { "$($image.Width)x$($image.Height)" } else { "none" }
    exit 0
  } catch { Start-Sleep -Milliseconds 250 }
}
"locked"
