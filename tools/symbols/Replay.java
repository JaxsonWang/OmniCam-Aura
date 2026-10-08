package local.omnicam.tools;

import java.nio.file.Files;
import java.nio.file.Path;
import local.jiege.hook.common.SymbolSearch;
import org.json.JSONArray;
import org.json.JSONObject;
import org.luckypray.dexkit.DexKitBridge;

/** 只读取 APK 中的 DEX，验证符号规则，不加载目标应用、不安装 Hook。 */
public final class Replay {
    public static void main(String[] args) throws Exception {
        System.load(args[0]);
        JSONObject spec = new JSONObject(Files.readString(Path.of(args[1]))).getJSONObject(args[2]);
        if (args.length == 5) {
            JSONObject overrides = new JSONObject(Files.readString(Path.of(args[4])));
            spec = SymbolSearch.withOverrides(spec, overrides.optJSONObject(args[2]));
        }
        try (DexKitBridge bridge = DexKitBridge.create(args[3])) {
            SymbolSearch result = SymbolSearch.run(bridge, spec);
            JSONObject resolved = new JSONObject();
            for (var entry : result.resolved.entrySet()) {
                resolved.put(entry.getKey(), new JSONArray(entry.getValue()));
            }
            System.out.println(new JSONObject().put("resolved", resolved)
                .put("failures", new JSONObject(result.failures)).toString(2));
        }
    }
}
