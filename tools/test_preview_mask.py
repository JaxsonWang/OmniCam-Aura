"""编译实际 Hook，以受控 GL／相机对象验证遮罩初始化边界。"""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

PROJECT = Path(__file__).resolve().parent.parent


class PreviewMaskTests(unittest.TestCase):
    def test_only_missing_shader_is_created_in_valid_gl_context(self):
        compiler = shutil.which("javac")
        runtime = shutil.which("java")
        self.assertIsNotNone(compiler, "遮罩测试需要 JDK")
        self.assertIsNotNone(runtime, "遮罩测试需要 JDK")
        sources = {
            "android/content/res/Resources.java": '''package android.content.res;
public class Resources {
 public static boolean missing;
 public int getIdentifier(String name, String type, String owner) {
  if (!type.equals("raw") || !owner.equals("com.oplus.camera")) throw new AssertionError();
  if (missing) return 0;
  return name.equals("texture_vertex_shader_inverse_mask") ? 11 : 12;
 }
}''',
            "android/app/AndroidAppHelper.java": '''package android.app;
public class AndroidAppHelper {
 public static AndroidAppHelper currentApplication() { return new AndroidAppHelper(); }
 public android.content.res.Resources getResources() { return new android.content.res.Resources(); }
}''',
            "android/opengl/EGL14.java": '''package android.opengl;
public class EGL14 {
 public static final Object EGL_NO_CONTEXT = new Object();
 public static Object current = new Object();
 public static Object eglGetCurrentContext() { return current; }
}''',
            "de/robv/android/xposed/XC_MethodHook.java": '''package de.robv.android.xposed;
public abstract class XC_MethodHook {
 public static class MethodHookParam {
  public Object thisObject;
  public boolean failed;
  public boolean hasThrowable() { return failed; }
 }
 protected void afterHookedMethod(MethodHookParam param) throws Throwable {}
 public void run(MethodHookParam param) throws Throwable { afterHookedMethod(param); }
}''',
            "de/robv/android/xposed/XposedBridge.java": '''package de.robv.android.xposed;
public class XposedBridge {
 public static XC_MethodHook hook;
 public static void hookAllConstructors(Class<?> type, XC_MethodHook value) { hook = value; }
}''',
            "local/jiege/hook/common/Log.java": '''package local.jiege.hook.common;
public class Log { public static void i(String tag, String message) {} }''',
            "local/jiege/hook/common/Symbols.java": '''package local.jiege.hook.common;
public class Symbols {
 public static int created;
 public static boolean valid = true;
 public static final Boolean inverseLight = false;
 public static class Shader {
  public Shader(int vertex, int fragment) {
   if (vertex != 11 || fragment != 12) throw new AssertionError();
   created++;
  }
 }
 public static class Canvas { public Shader mask; }
 public static Symbols get() { return new Symbols(); }
 public java.lang.reflect.Field field(String id) {
  if (!id.equals("PreviewMask.shader")) throw new AssertionError();
  try { return Canvas.class.getField("mask"); } catch (Exception e) { throw new AssertionError(e); }
 }
 public Class<?> cls(String id) { return Canvas.class; }
 public Object call(String id, Object target) { return valid; }
 public Object get(String id, Object target) {
  if (!id.equals("InverseLight.supportCache") || target != null) throw new AssertionError();
  return inverseLight;
 }
}''',
            "TestMask.java": '''import android.opengl.EGL14;
import android.content.res.Resources;
import de.robv.android.xposed.XC_MethodHook.MethodHookParam;
import de.robv.android.xposed.XposedBridge;
import local.jiege.hook.common.Symbols;
import local.jiege.hook.pop.PreviewMaskShader;
public class TestMask {
 static MethodHookParam param() {
  MethodHookParam param = new MethodHookParam();
  param.thisObject = new Symbols.Canvas();
  return param;
 }
 static void check(boolean result) { if (!result) throw new AssertionError(); }
 static void rejects(MethodHookParam param) throws Throwable {
  try { XposedBridge.hook.run(param); throw new AssertionError("expected failure"); }
  catch (IllegalStateException expected) { check(((Symbols.Canvas)param.thisObject).mask == null); }
 }
 public static void main(String[] args) throws Throwable {
  PreviewMaskShader.install();
  MethodHookParam first = param();
  XposedBridge.hook.run(first);
  Object shader = ((Symbols.Canvas)first.thisObject).mask;
  check(shader != null && Symbols.created == 1 && !Symbols.inverseLight);
  XposedBridge.hook.run(first);
  check(((Symbols.Canvas)first.thisObject).mask == shader && Symbols.created == 1);
  MethodHookParam failed = param(); failed.failed = true;
  XposedBridge.hook.run(failed); check(Symbols.created == 1);
  EGL14.current = EGL14.EGL_NO_CONTEXT;
  rejects(param()); check(Symbols.created == 1);
  EGL14.current = new Object(); Resources.missing = true;
  rejects(param()); check(Symbols.created == 1);
  Resources.missing = false; Symbols.valid = false;
  rejects(param()); check(Symbols.created == 2 && !Symbols.inverseLight);
 }
}''',
        }
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            for name, content in sources.items():
                path = work / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            production = PROJECT / "app/src/main/java/local/jiege/hook/pop/PreviewMaskShader.java"
            subprocess.run([compiler, "-d", str(work), str(production),
                            *(str(work / name) for name in sources)], check=True)
            subprocess.run([runtime, "-cp", str(work), "TestMask"], check=True)


if __name__ == "__main__":
    unittest.main()
