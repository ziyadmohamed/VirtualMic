# حل نهائي - تحميل DevCon واستخدامه

## المشكلة
pnputil مفيهوش `/add-device` - محتاجين **DevCon** لإنشاء Software Device.

---

## الحل السريع: تحميل DevCon

### الخطوة 1: تحميل DevCon

**الخيار أ - من GitHub** (موصى به):
```
https://github.com/microsoft/Windows-driver-samples/raw/main/tools/devcon/devcon.exe
```

**الخيار ب - من WDK** (لو مثبت):
```
C:\Program Files (x86)\Windows Kits\10\Tools\x64\devcon.exe
```

**حمّل** `devcon.exe` وحطه في:
```
C:\Users\MU\Downloads\devcon.exe
```

---

### الخطوة 2: إنشاء Device Instance

افتح **PowerShell كـ Administrator**:

```powershell
cd C:\Users\MU\Downloads
.\devcon.exe install "C:\Users\MU\Downloads\StMicDriver-Output\Release\package\SimpleAudioSample.inf" Root\SimpleAudioSample
```

---

### الخطوة 3: التحقق

```powershell
# شوف الـ device
devmgmt.msc
```

ابحث عن: **"Virtual Audio Device (WDM) - Simple Audio Sample"**

---

## البديل: Python Script

عملتلك script اسمه `create_device.py` - شغله كـ Admin:

```powershell
# PowerShell كـ Administrator  
python create_device.py
```

---

## لو DevCon مش متاح

نستخدم **Device Manager** يدوياً:

1. افتح Device Manager (`devmgmt.msc`)
2. **Action** → **Add legacy hardware**
3. **Next** → **Install the hardware that I manually select from a list**
4. اختر **Sound, video and game controllers** → **Next**
5. **Have Disk...**
6. Browse: `C:\Users\MU\Downloads\StMicDriver-Output\Release\package`
7. اختر `SimpleAudioSample.inf`
8. اختر **Virtual Audio Device (WDM) - Simple Audio Sample**
9. **Next** → **Finish**

---

## تحميل DevCon الآن

**رابط مباشر**:
```
https://github.com/microsoft/Windows-driver-samples/raw/main/tools/devcon/devcon.exe
```

أو ابحث في Google عن: `devcon.exe download microsoft`

---

**بعد ما تحمل DevCon، قولي!** 🚀
