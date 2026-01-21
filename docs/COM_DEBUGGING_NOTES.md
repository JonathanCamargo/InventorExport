# Inventor COM Integration: Debugging Notes

Lessons learned from debugging pywin32 + Autodesk Inventor COM automation.

## The Problem

STEP geometry files were not being generated when running `inventorexport` against a real Inventor assembly, despite no visible errors.

---

## Issues & Solutions

### 1. gen_py Cache Corruption

**Symptom:** `'_dispobj_'` error on connection

**Cause:** pywin32's gen_py cache stores type information for COM objects. This cache can become corrupted or mismatched with the installed Inventor version.

**Fix:** Use dynamic dispatch instead of relying on cached type info:

```python
# Instead of:
app = win32com.client.GetActiveObject("Inventor.Application")

# Use:
unknown = pythoncom.GetActiveObject("Inventor.Application")
dispatch = unknown.QueryInterface(pythoncom.IID_IDispatch)
app = win32com.client.dynamic.Dispatch(dispatch)
```

---

### 2. Early-Bound COM Objects Missing Attributes

**Symptom:**
- `AssetValue has no attribute 'Value'`
- `Asset has no attribute 'PhysicalPropertiesAsset'`

**Cause:** gen_py creates early-bound wrappers that think they know the object's interface. When the cache is wrong, attribute access fails even though the COM object has those properties.

**Fix:** Create a `late_bind()` utility to convert any COM object to late-binding:

```python
def late_bind(obj):
    """Convert early-bound COM object to late-binding."""
    if obj is None:
        return None
    try:
        if hasattr(obj, '_oleobj_'):
            return win32com.client.dynamic.Dispatch(obj._oleobj_)
        return obj
    except Exception:
        return obj
```

Apply this to any COM object that might have come from early-bound code.

---

### 3. VBA Property Assignment Syntax

**Symptom:** `'method' object does not support item assignment`

**Cause:** VBA's `oOptions.Value("key") = value` syntax doesn't translate to Python. In Python, `options.Value("key")` looks like a method call, not a property assignment.

**Fix:**
- Use `options.Item("key", value)` if available
- Or skip setting the option and use defaults
- The NameValueMap indexed property assignment is problematic in pywin32

---

### 4. Objects from Traversal Not Late-Bound

**Symptom:** STEP export silently fails

**Cause:** When traversing an assembly, COM objects obtained via property access (like `occ.Definition.Document`) inherit the binding mode of their parent. If any ancestor was early-bound, the object may be early-bound too.

**Fix:** Apply `late_bind()` to objects before passing them to other COM methods:

```python
def export_step(app, document, output_path):
    document = late_bind(document)  # Ensure late-binding
    # ... rest of export
```

---

### 5. Relative Paths Don't Work

**Symptom:** STEP export completes without error but file doesn't exist

**Cause:** Inventor's COM API runs in Inventor's process, not your Python process. It doesn't share your working directory, so `"Part1.stp"` means nothing to it.

**Fix:** Always use absolute paths when passing filenames to COM:

```python
# Instead of:
data_medium.FileName = str(output_path)

# Use:
data_medium.FileName = str(output_path.absolute())
```

---

## Debugging Strategies

### 1. Use print() Over logging

When logging configuration is uncertain, `print()` statements bypass all logging level/handler issues:

```python
print(f"[DEBUG] About to call SaveCopyAs...")
translator.SaveCopyAs(document, context, options, data_medium)
print(f"[DEBUG] SaveCopyAs completed")
```

### 2. Trace the Data Flow

Follow objects through the code to see where binding mode might change:
- Where was the object created?
- Was it from a late-bound or early-bound parent?
- Is it being passed to a method that expects a specific type?

### 3. Check Object Types

Print objects to see what you're dealing with:

```python
print(f"Translator: {translator}")  # <COMObject <unknown>> = late-bound
print(f"Document: {document}")      # Integer = probably wrong!
```

### 4. Clear the gen_py Cache

When all else fails, clear the cache and start fresh:

```python
import win32com
import shutil
shutil.rmtree(win32com.__gen_path__, ignore_errors=True)
```

---

## Summary

| Problem | Solution |
|---------|----------|
| gen_py cache issues | Use `dynamic.Dispatch()` for late-binding |
| Missing attributes | Apply `late_bind()` to convert objects |
| Property assignment | Use method syntax or skip |
| Silent failures | Use absolute paths |
| Can't see errors | Use `print()` instead of logging |

The core lesson: **pywin32's early-binding (gen_py) is convenient when it works, but fragile. When automating complex COM applications like Inventor, prefer late-binding throughout.**
