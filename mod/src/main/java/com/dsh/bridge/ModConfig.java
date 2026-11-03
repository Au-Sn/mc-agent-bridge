package com.dsh.bridge;

/**
 * ModConfig —— ★★2.58.0（79.534 发布准备）✗★★：把"模组的环境事实"收口成**可覆盖的配置** ✓
 *
 * <p>★为什么要有它✗★：原来假人名 `"Bot"`、直连端口 `8766`、token 文件路径散在
 * {@link DshBridgeMod} / {@link HttpBridge} / {@link BotSkin} 三个类里写死 ✗
 * ⇒ 换个玩家名/端口/存档就要改源码重编 ✗ —— 上传 GitHub 给别人用时这是硬伤 ✗
 *
 * <p>★取值顺序（每一项都一样）✗★：
 * <ol>
 *   <li>**JVM 系统属性**（`-Ddshbridge.bot=…`）—— 优先级最高 ✓</li>
 *   <li>**环境变量**（`BOT_NAME` / `DSH_PORT` / `HTTP_TOKEN_FILE`，与仓库根 `dsh.env` 同名 ✓）</li>
 *   <li>**默认值** —— ★与本轮之前**逐字节相同**✗★（Bot / 8766 / 相对 config 路径）</li>
 * </ol>
 *
 * <p>★纪律✗★：这里**只读**配置 ✗ 不改任何业务逻辑 ✓；默认情况下三个值都与旧版完全一致 ✓
 * ⇒ tick 顺序/回执文本/判据全部不变 ✓
 */
public final class ModConfig {

    private ModConfig() {
    }

    /** 假人名（默认 `Bot` ✓；`/dshevents watch <name>` 仍可运行时改观测量，两者独立 ✓） */
    public static final String BOT_NAME = resolve("dshbridge.bot", "BOT_NAME", "Bot");

    /** 直连 HTTP 端口（默认 8766 ✓；只绑 127.0.0.1 ✗ 不对外 ✓） */
    public static final int HTTP_PORT = resolveInt("dshbridge.port", "DSH_PORT", 8766);

    /** token 文件（★空串 ⇒ 用默认相对路径 `config/dshbridge/http_token.txt`✗★） */
    public static final String TOKEN_FILE = resolve("dshbridge.tokenFile", "HTTP_TOKEN_FILE", "");

    static String resolve(String prop, String env, String dflt) {
        String v = null;
        try {
            v = System.getProperty(prop);
        } catch (Exception ignored) {
            // ★读属性失败绝不崩游戏✗★（默认值照用 ✓）
            v = null;
        }
        if (v == null || v.trim().isEmpty()) {
            try {
                v = System.getenv(env);
            } catch (Exception ignored) {
                v = null;
            }
        }
        if (v == null || v.trim().isEmpty()) {
            return dflt;
        }
        return v.trim();
    }

    static int resolveInt(String prop, String env, int dflt) {
        String v = resolve(prop, env, "");
        if (v.isEmpty()) {
            return dflt;
        }
        try {
            int n = Integer.parseInt(v.trim());
            if (n > 0 && n < 65536) {
                return n;
            }
        } catch (NumberFormatException ignored) {
            // ★给错了就用默认值 ✗ 但不许静默：第一次用时会由 http_server 事件自报端口 ✓
        }
        return dflt;
    }
}
