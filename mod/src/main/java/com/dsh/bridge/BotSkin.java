package com.dsh.bridge;

import com.mojang.authlib.properties.Property;
import com.mojang.brigadier.CommandDispatcher;
import com.mojang.brigadier.arguments.StringArgumentType;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.Commands;
import net.minecraft.network.chat.Component;
import net.minecraft.network.protocol.game.ClientboundPlayerInfoRemovePacket;
import net.minecraft.network.protocol.game.ClientboundPlayerInfoUpdatePacket;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerPlayer;
import net.minecraftforge.event.RegisterCommandsEvent;
import net.minecraftforge.event.TickEvent;
import net.minecraftforge.event.entity.player.PlayerEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;
import net.minecraftforge.server.ServerLifecycleHooks;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Base64;
import java.util.EnumSet;
import java.util.List;

/**
 * ★★给假人 Bot 换皮肤（v2.11.4 ✓ 用户点名 ✓）★★
 *
 * <p>为什么不能靠资源包 ✗（2026-09-20 实测 ✓ 不是推测 ✓）：
 * <ul>
 *   <li>资源包"覆盖默认皮肤"（{@code assets/minecraft/textures/entity/player/{wide,slim}/*.png}）
 *       的那条路，只对**没有皮肤的玩家**有效 ✓</li>
 *   <li>而这个假人的 UUID 是 <b>v4</b>（{@code 49e96464-…-46b3-…}）✗，
 *       名字 "Bot" 的<b>离线</b> UUID 是 v3（{@code bb19ef2f-…-39a8-…}）✗ ⇒ <b>两者不同</b> ✗
 *       ⇒ 说明它挂的是<b>真实身份</b> ⇒ 客户端会按那个身份去拉真皮肤 ✗</li>
 *   <li>实测佐证 ✓：包已启用 ✓ 已重载 ✓（{@code Reloading ResourceManager: … file/DSH_BlueFish_DeepSeek}）
 *       而且 314 个 mod / 资源包里<b>只有它</b>提供玩家贴图 ✓ ⇒ 一点变化都没有 ✗</li>
 * </ul>
 *
 * <p>正解 ✓：直接给它的 GameProfile 塞一个 {@code textures} 属性 ✓
 * （内容是一段 base64 的 JSON：{@code {"textures":{"SKIN":{"url":"…"}}} }✓）
 * ⇒ 客户端就会**自己去那个 URL 拉 PNG** ✓ —— 所以还要有个地方放 PNG ✓
 * 见 {@code tools/skin_server.py}（本地 HTTP ✓ ★它的访问日志就是判据★ ✓）。
 *
 * <p>用法 ✓：
 * <pre>
 *   dsh_bot_skin.txt             ← 游戏目录下的这个文件，内容就一行 URL ✓
 *   /dshtskin status             看当前状态 ✓
 *   /dshtskin set &lt;url&gt;         设 URL（顺手写回那个文件 ✓）
 *   /dshtskin apply              重新注入 ＋ 重新广播 profile ✓
 *   /dshtskin clear              摘掉 textures 属性 ✓
 * </pre>
 *
 * <p>⚠ 这条路**唯一没验的**一环 ✗：单机里客户端认不认 {@code http://127.0.0.1:…} 这种非 https 地址 ✓
 * 判据现成 ✓：skin_server 的日志里**有没有出现 GET** ✓ —— 有就是成了 ✓ 没有就是被拒了 ✓
 */
@Mod.EventBusSubscriber(modid = "dshbridge")
public final class BotSkin {

    /** ★79.534✗★：假人名走配置（默认仍是 "Bot" ✓；`-Ddshbridge.bot=` 可覆盖 ✓） */
    private static final String BOT = ModConfig.BOT_NAME;
    /** 游戏目录下的一行配置文件 ✓（相对路径＝当前工作目录＝实例目录 ✓） */
    private static final Path CFG = Paths.get("dsh_bot_skin.txt");
    private static volatile String url = "";
    private static volatile boolean loaded = false;
    /** 登录后再补一次（客户端那时已经建好实体 ✓ 见类的注释 ✓） */
    private static int reapplyIn = -1;

    private BotSkin() {
    }

    // ── 载入 / 保存 ──────────────────────────────────────────────────────────
    private static void loadCfg() {
        loaded = true;
        try {
            if (Files.isRegularFile(CFG)) {
                String s = Files.readString(CFG, StandardCharsets.UTF_8).trim();
                if (!s.isEmpty() && !s.startsWith("#")) {
                    url = s.split("\\s+")[0];
                }
            }
        } catch (Exception ignored) {
            // ★读不到就当作没配 ✓ 绝不猜 ✓
        }
    }

    private static void saveCfg() {
        try {
            Files.writeString(CFG, url + "\n", StandardCharsets.UTF_8);
        } catch (Exception ignored) {
            // 写不进去 ⇒ 下次重启会把皮肤 URL 忘掉（不许静默）
            System.out.println("[dshtskin] 配置写不进（下次重启会忘） ✗ " + ignored);
        }
    }

    // ── 注入 ────────────────────────────────────────────────────────────────
    private static String b64(String u) {
        String json = "{\"textures\":{\"SKIN\":{\"url\":\"" + u + "\"}}}";
        return Base64.getEncoder().encodeToString(json.getBytes(StandardCharsets.UTF_8));
    }

    /** 把 textures 属性塞进它的 profile ✓ 然后**重新广播**一次 profile ✗（客户端才会重读 ✓） */
    private static void apply(ServerPlayer p, String why) {
        if (url.isEmpty()) {
            return;
        }
        try {
            p.getGameProfile().getProperties().removeAll("textures");
            p.getGameProfile().getProperties().put("textures", new Property("textures", b64(url)));
        } catch (Exception e) {
            System.out.println("[dshtskin] 注入失败 ✗ " + e);
            return;
        }
        MinecraftServer srv = ServerLifecycleHooks.getCurrentServer();
        if (srv != null) {
            try {
                srv.getPlayerList().broadcastAll(
                        new ClientboundPlayerInfoRemovePacket(List.of(p.getUUID())));
                srv.getPlayerList().broadcastAll(
                        new ClientboundPlayerInfoUpdatePacket(
                                EnumSet.of(ClientboundPlayerInfoUpdatePacket.Action.ADD_PLAYER,
                                        ClientboundPlayerInfoUpdatePacket.Action.UPDATE_LISTED,
                                        ClientboundPlayerInfoUpdatePacket.Action.UPDATE_LATENCY,
                                        ClientboundPlayerInfoUpdatePacket.Action.UPDATE_GAME_MODE,
                                        ClientboundPlayerInfoUpdatePacket.Action.UPDATE_DISPLAY_NAME),
                                List.of(p)));
            } catch (Exception e) {
                System.out.println("[dshtskin] 广播失败 ✗ " + e);
            }
        }
        System.out.println("[dshtskin] 已给 " + p.getGameProfile().getName() + " 注入 textures（" + why + "）"
                + " url=" + url);
    }

    private static ServerPlayer bot() {
        MinecraftServer srv = ServerLifecycleHooks.getCurrentServer();
        return srv == null ? null : srv.getPlayerList().getPlayerByName(BOT);
    }

    // ── 事件 ────────────────────────────────────────────────────────────────
    @SubscribeEvent
    public static void onLogin(PlayerEvent.PlayerLoggedInEvent e) {
        if (!(e.getEntity() instanceof ServerPlayer p)) {
            return;
        }
        if (!BOT.equals(p.getGameProfile().getName())) {
            return;
        }
        if (!loaded) {
            loadCfg();
        }
        if (url.isEmpty()) {
            System.out.println("[dshtskin] 假人登录了，但 " + CFG.toAbsolutePath()
                    + " 里没配 URL ⇒ 不动它 ✓（本文件由 /dshtskin set 生成 ✓）");
            return;
        }
        apply(p, "login");
        reapplyIn = 40;                    // ★2 秒后再补一次★ ✓（那时客户端实体已建好 ✓ 值得一试 ✓）
    }

    @SubscribeEvent
    public static void onServerTick(TickEvent.ServerTickEvent e) {
        if (e.phase != TickEvent.Phase.END || reapplyIn < 0) {
            return;
        }
        if (--reapplyIn == 0) {
            reapplyIn = -1;
            ServerPlayer p = bot();
            if (p != null) {
                apply(p, "login+2s");
            }
        }
    }

    @SubscribeEvent
    public static void onRegisterCommands(RegisterCommandsEvent e) {
        CommandDispatcher<CommandSourceStack> d = e.getDispatcher();
        d.register(Commands.literal("dshtskin")
                .then(Commands.literal("status").executes(c -> {
                    if (!loaded) {
                        loadCfg();
                    }
                    boolean has = false;
                    ServerPlayer p = bot();
                    if (p != null) {
                        has = !p.getGameProfile().getProperties().get("textures").isEmpty();
                    }
                    ok(c.getSource(), "dshtskin url=" + (url.isEmpty() ? "(none)" : url)
                            + " bot=" + (p == null ? "(not online)" : "online")
                            + " textures_injected=" + has
                            + " cfg=" + CFG.toAbsolutePath());
                    return 1;
                }))
                .then(Commands.literal("set")
                        .then(Commands.argument("url", StringArgumentType.greedyString()).executes(c -> {
                            url = StringArgumentType.getString(c, "url").trim();
                            saveCfg();
                            ServerPlayer p = bot();
                            if (p != null) {
                                apply(p, "set");
                            }
                            ok(c.getSource(), "dshtskin set ok url=" + url
                                    + (p == null ? " (no bot online - it will apply on next login)" : ""));
                            return 1;
                        })))
                .then(Commands.literal("apply").executes(c -> {
                    if (!loaded) {
                        loadCfg();
                    }
                    ServerPlayer p = bot();
                    if (p == null) {
                        ok(c.getSource(), "dshtskin apply: no bot online");
                        return 1;
                    }
                    if (url.isEmpty()) {
                        ok(c.getSource(), "dshtskin apply: no url configured");
                        return 1;
                    }
                    apply(p, "manual");
                    ok(c.getSource(), "dshtskin apply done url=" + url);
                    return 1;
                }))
                .then(Commands.literal("reload").executes(c -> {
                    loadCfg();
                    ok(c.getSource(), "dshtskin reload url=" + (url.isEmpty() ? "(none)" : url));
                    return 1;
                }))
                .then(Commands.literal("clear").executes(c -> {
                    ServerPlayer p = bot();
                    if (p != null) {
                        p.getGameProfile().getProperties().removeAll("textures");
                        apply(p, "clear");
                    }
                    url = "";
                    saveCfg();
                    ok(c.getSource(), "dshtskin cleared");
                    return 1;
                })));
    }

    private static void ok(CommandSourceStack src, String msg) {
        src.sendSuccess(() -> Component.literal(msg), false);
    }
}
