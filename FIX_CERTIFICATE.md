# ✅ الحل الأسهل - تعطيل Driver Signature Enforcement

## المشكلة
الـ certificate commands فشلت لأنها محتاجة صلاحيات Admin.

## الحل البسيط (5 دقائق)

### الخطوة 1: افتح Advanced Boot Options

افتح **PowerShell** (مش محتاج Admin):

```powershell
shutdown /r /o /f /t 10
```

الكومبيوتر هيعمل restart بعد 10 ثواني وهيفتح قائمة زرقاء.

---

### الخطوة 2: في القائمة الزرقاء

اتبع الخطوات دي:

1. **Troubleshoot** 
2. **Advanced options**
3. **Startup Settings**
4. **Restart**

---

### الخطوة 3: بعد الـ Restart

هتظهر قائمة مرقمة، اضغط:

**7** أو **F7** → **"Disable driver signature enforcement"**

Windows هيقلع عادي بس **بدون فحص توقيعات Drivers**.

---

### الخطوة 4: ثبت الـ Driver

بعد ما Windows يفتح، افتح **PowerShell كـ Administrator**:

```powershell
cd "C:\Users\MU\Downloads\StMicDriver-Output\Release\package"
pnputil /add-driver SimpleAudioSample.inf /install
```

**المرة دي هينجح!** ✅

---

### الخطوة 5: التحقق

افتح **Device Manager** (`devmgmt.msc`):
- ابحث عن **"Virtual Audio Device (WDM) - Simple Audio Sample"**
- يجب أن يظهر تحت **"Sound, video and game controllers"**

---

## ملاحظات مهمة

### هل يجب تكرار هذا في كل مرة؟
**لا!** Driver Signature Enforcement يُعطّل فقط **لهذه الجلسة**. 
لكن بعد تثبيت الـ driver، هيفضل شغال حتى بعد Restart عادي.

### التأثير الأمني؟
**منخفض** - بمجرد تثبيت الـ driver، Windows العادي هيرجع في الـ restart التالي.

### إذا أردت التعطيل الدائم (غير موصى به):
```powershell
# PowerShell كـ Administrator
bcdedit /set nointegritychecks on
```

---

## جاهز؟

1. نفذ الأمر: `shutdown /r /o /f /t 10`
2. اتبع الخطوات في القائمة الزرقاء
3. اضغط **7** أو **F7**
4. ثبت الـ driver بعد الإقلاع

**قولي لما تخلص!** 🚀
