package local.jiege.hook.filters;
import android.content.Context;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedBridge;
import de.robv.android.xposed.XposedHelpers;
import java.util.HashMap;
import java.util.List;
import local.jiege.hook.common.Log;

/** Adds 清透 and 琥珀 to the camera and SDK filter groups. */
public final class FilterGroupInjector {
    private static final String TAG = "AuraFilters";
    private static final String SDK = "com.oplus.ocs.camera.ipusdk.processunit.filter.list.FilterGroupManager";
    private static final String APP = "com.oplus.camera.filter.FilterGroupManager";
    private static final String CAMERA = "com.oplus.camera";
    private static final String NIGHT_GROUP = "sNightFilterGroup";
    public static void installCamera(ClassLoader classLoader) {
        try {
            Class<?> sdk = XposedHelpers.findClass(SDK, classLoader);
            XposedBridge.hookAllMethods(sdk, "init", new XC_MethodHook() {
                @Override protected void afterHookedMethod(MethodHookParam param) { injectAll(sdk, null, classLoader); }
            });
        } catch (Throwable error) {
            Log.e(TAG, "SDK filter group hook failed", error);
        }
        try {
            Class<?> app = XposedHelpers.findClass(APP, classLoader);
            XposedHelpers.findAndHookMethod(app, "initFromIpu", Context.class, HashMap.class, new XC_MethodHook() {
                @Override protected void afterHookedMethod(MethodHookParam param) { injectAll(app, (Context) param.args[0], classLoader); }
            });
        } catch (Throwable error) {
            Log.e(TAG, "app filter group hook failed", error);
        }
    }
    private static void injectAll(Class<?> manager, Context context, ClassLoader loader) {
        for (FilterScope scope : FilterScope.values()) {
            for (String groupName : scope.groups) {
                try {
                    Object group = XposedHelpers.getStaticObjectField(manager, groupName);
                    if (group != null) inject(group, NIGHT_GROUP.equals(groupName), FilterCatalog.get(scope).entries(), context);
                } catch (Throwable error) {
                    Log.e(TAG, groupName + " injection failed", error);
                }
            }
        }
    }
    private static int inject(Object group, boolean backOnly, List<FilterEntry> entries, Context context) {
        String add = backOnly ? "addBack" : "addFrontAndBack";
        int head = 1;  // position 0 is 标准
        int added = 0;
        for (FilterEntry entry : entries) {
            @SuppressWarnings("unchecked") List<String> types = (List<String>) XposedHelpers.getObjectField(group, "mBackTypeList");
            if (types != null && types.contains(entry.id)) {
                if (entry.placement == FilterEntry.Placement.HEAD) head++;
                continue;
            }
            Object name;
            if (context == null) {
                name = "R.string." + entry.nameResource;
            } else {
                int id = context.getResources().getIdentifier(entry.nameResource, "string", CAMERA);
                if (id == 0) throw new IllegalStateException("Missing name resource " + entry.nameResource);
                name = Integer.valueOf(id);
            }
            if (entry.placement == FilterEntry.Placement.HEAD) {
                XposedHelpers.callMethod(group, add, Integer.valueOf(head++), entry.id, name);
            } else {
                XposedHelpers.callMethod(group, add, entry.id, name);
            }
            added++;
        }
        return added;
    }
}
