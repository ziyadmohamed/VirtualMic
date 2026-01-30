# خطوات تثبيت StMicDriver

## ✅ الملفات جاهزة في:
`C:\Users\MU\Downloads\StMicDriver-Output\Release\package\`

الملفات:
- SimpleAudioSample.sys (61 KB)
- SimpleAudioSample.inf (15 KB)
- simpleaudiosample.cat (3.6 KB)

---

## الخطوة 1: تفعيل Test Signing

**⚠️ مهم جداً - يجب عمل هذا أولاً!**

افتح **PowerShell كـ Administrator** واكتب:

```powershell
bcdedit /set TESTSIGNING ON
```

بعدها **يجب عمل Restart للكومبيوتر!**

بعد الـ Restart، هتلاقي watermark في الزاوية اليمين السفلية من الشاشة بيقول "Test Mode".

---

## الخطوة 2: تثبيت Driver (بعد Restart)

افتح **PowerShell كـ Administrator** مرة تانية واكتب:

```powershell
cd "C:\Users\MU\Downloads\StMicDriver-Output\Release\package"

# تثبيت Driver
pnputil /add-driver SimpleAudioSample.inf /install
```

---

## الخطوة 3: التحقق من التثبيت

### الطريقة 1: Device Manager
1. اضغط `Win + X` واختر "Device Manager"
2. ابحث عن **"Virtual Audio Device (WDM) - Simple Audio Sample"**
3. يجب أن يظهر تحت **"Sound, video and game controllers"**
4. لا يجب أن يكون عليه علامة تعجب صفراء ⚠️

### الطريقة 2: Sound Settings
1. كليك يمين على أيقونة الصوت في Taskbar
2. اختر "Sound settings"
3. اذهب لـ "Advanced sound settings" أو "Sound Control Panel"
4. في تاب "Recording"، يجب أن ترى **"Microphone (Virtual Audio Device)"**

---

## إذا واجهت مشاكل

### المشكلة: bcdedit يعطي "Access Denied"
**الحل**: لازم تشغل PowerShell كـ **Administrator**
- اضغط `Win + X`
- اختر "Windows PowerShell (Admin)" أو "Terminal (Admin)"

### المشكلة: Driver لا يظهر في Device Manager
**الحل**: 
1. تأكد إنك عملت Restart بعد `bcdedit`
2. جرب تشغيل الأمر مرة تانية:
   ```powershell
   pnputil /add-driver SimpleAudioSample.inf /install
   ```

### المشكلة: Driver يظهر بعلامة تعجب صفراء
**الحل**:
1. كليك يمين على الـ device → Properties
2. شوف الخطأ في "Device status"
3. جرب:
   ```powershell
   # إزالة Driver
   pnputil /delete-driver SimpleAudioSample.inf /uninstall
   
   # إعادة التثبيت
   pnputil /add-driver SimpleAudioSample.inf /install
   ```

---

## بعد التثبيت الناجح

**الخطوة التالية**: 
1. ✅ نعدل Python receiver ليرسل صوت للـ Driver
2. ✅ نعدل Android app للـ WiFi streaming
3. ✅ نختبر النظام كامل

🎉 **أنت قريب جداً من النهاية!**
