# أوامر Restart Audio Services بدون Restart الكومبيوتر

## الطريقة 1: Restart Audio Services (موصى بها)

افتح **PowerShell كـ Administrator** واكتب:

```powershell
# إيقاف Audio Services
Stop-Service -Name "Audiosrv" -Force
Stop-Service -Name "AudioEndpointBuilder" -Force

# بدء Audio Services من جديد
Start-Service -Name "AudioEndpointBuilder"
Start-Service -Name "Audiosrv"

# إعادة تحميل الـ Plug and Play devices
powershell -Command "pnputil /scan-devices"
```

---

## الطريقة 2: إعادة فحص Hardware Changes

```powershell
# إعادة فحص كل Hardware
pnputil /scan-devices

# أو استخدام Device Manager من الكوماند لاين
powershell -Command "Get-PnpDevice | Where-Object {$_.Class -eq 'MEDIA'} | Disable-PnpDevice -Confirm:$false; Start-Sleep 2; Get-PnpDevice | Where-Object {$_.Class -eq 'MEDIA'} | Enable-PnpDevice -Confirm:$false"
```

---

## الطريقة 3: أمر واحد شامل (الأسهل)

```powershell
# PowerShell كـ Administrator - نفذ الكود ده كله مرة واحدة
Restart-Service -Name "Audiosrv" -Force
Restart-Service -Name "AudioEndpointBuilder" -Force
pnputil /scan-devices
Start-Sleep -Seconds 3
Get-PnpDevice -Class 'MEDIA' | Where-Object {$_.Status -eq 'Error' -or $_.Status -eq 'Unknown'} | Disable-PnpDevice -Confirm:$false
Start-Sleep -Seconds 2
Get-PnpDevice -Class 'MEDIA' | Enable-PnpDevice -Confirm:$false
```

---

## الطريقة 4: إذا مش ظاهر بعد كده

```powershell
# حاول تشغيل الـ driver setup يدوياً
cd "C:\Users\MU\Downloads\StMicDriver-Output\Release\package"

# إزالة Driver (لو موجود)
pnputil /delete-driver SimpleAudioSample.inf /uninstall /force

# إعادة التثبيت
pnputil /add-driver SimpleAudioSample.inf /install

# Restart Audio
Restart-Service -Name "Audiosrv" -Force
```

---

## بعد تنفيذ الأوامر

تحقق من Device Manager:
```powershell
# عرض كل Audio Devices
Get-PnpDevice -Class 'MEDIA' | Select-Object Status, FriendlyName, InstanceId
```

أو افتح Device Manager GUI:
```powershell
devmgmt.msc
```

وشوف "Sound, video and game controllers" → يجب أن تجد "Virtual Audio Device (WDM) - Simple Audio Sample"
