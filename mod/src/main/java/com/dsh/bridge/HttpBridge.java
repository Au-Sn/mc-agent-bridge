package com.dsh.bridge;

import com.mojang.brigadier.context.CommandContext;
import net.minecraft.commands.CommandSource;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.network.chat.Component;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;

import java.util.ArrayList;
import java.util.List;

/**
 * HttpBridge —— ★★2.57.0（A2/S1 结构第二刀）✗★★：**HTTP 服务边界**（从 {@link DshBridgeMod} 原样搬出）
 *
 * <p>★只搬不改✗★（ADR-5）：accept 线程池／单线程世界车道／token 文件与校验／拒 Origin／
 * {@code /raw} 白名单／请求账本／{@code /dshhttp}／{@code /dshreqs} 与
 * {@code httpRunRaw/httpRunCommand} 逐行搬到这里，**逻辑/回执文本/tick 顺序一字未动** ✗
 *
 * <p>★边界规则（与搬出前一致）✗★：
 * <ul>
 *   <li>世界命令必须回服务器线程串行执行 ⇒ {@code HTTP_WORLD_LANE} 单线程车道 ✓</li>
 *   <li>只读/健康检查只走 worker 池 ⇒ {@code /health} 不被长命令堵住 ✓</li>
 *   <li>{@code /cmd} 与 {@code /raw} 必须带 {@code X-DSH-Token}；任何带 Origin 的请求一律拒 ✓</li>
 * </ul>
 *
 * <p>★为什么事件出口不在这里✗★：{@code errata_guard_test} 的 E11 只扫 {@code DshBridgeMod.java}
 * 对账事件名 ⇒ 事件字面量留在主类，这里只调用 {@code DshBridgeMod.httpEventServer/httpEventError} ✓
 */
class HttpBridge {

    // ★★2.56.0（A3 HTTP 加固）✗★★ 三个边界各一把锁：
    //   ① **线程池**：accept 线程只收连接 ✗ 每个连接交给 worker ⇒ /health 不再被长命令堵死 ✓
    //   ② **世界车道**：/cmd 与 /raw **只走一条单线程车道** ⇒ 世界写仍然**串行且保序** ✓
    //      （★绝不把世界写并行化✗★ —— 服务器只有一条线程，写必须排队 ✓）
    //   ③ **来源校验**：token（config/dshbridge/http_token.txt）＋ 拒 Origin（浏览器 CSRF）＋
    //      /raw 白名单（只放"拉假人/摆测试方块/给假人换工具"这些**现成真用法** ✓）
    //   ★79.534✗★：端口不再写死 ✗ 走 `-Ddshbridge.port=` / env `DSH_PORT` / 默认 8766 ✓
    public static final int HTTP_PORT = ModConfig.HTTP_PORT;
    static java.net.ServerSocket HTTP_SS = null;
    static Thread HTTP_THREAD = null;                  // accept 线程（保留这个字段：旧读者/回滚用）
    static java.util.concurrent.ThreadPoolExecutor HTTP_POOL = null;
    static java.util.concurrent.ExecutorService HTTP_WORLD_LANE = null;
    static final java.util.concurrent.atomic.AtomicLong HTTP_HITS = new java.util.concurrent.atomic.AtomicLong();
    static final java.util.concurrent.atomic.AtomicLong HTTP_REQ_SEQ = new java.util.concurrent.atomic.AtomicLong();
    static volatile String HTTP_TOKEN = "";
    static volatile String HTTP_TOKEN_SRC = "none";
    static volatile long HTTP_LANE_MS_MAX = 0L;
    static final int HTTP_WORKERS = 8;
    static final int HTTP_LANE_TIMEOUT_MS = 35000;
    static final int HTTP_CONTENT_LIMIT = 65536;
    /** ★回滚开关✗★：`-Ddshbridge.http.pool=false` ⇒ 回到旧的"accept 线程内联处理" ✓ */
    static final boolean HTTP_POOL_ON = !"false".equalsIgnoreCase(
            System.getProperty("dshbridge.http.pool", "true"));
    /** A7：最近请求账本（id/op/status/ms）✗ 只读命令 `/dshreqs` 取走 ✓ 有界 ✓ */
    static final java.util.ArrayDeque<String> HTTP_REQS = new java.util.ArrayDeque<>();
    static final int HTTP_REQS_KEEP = 64;

    /** token 文件路径（★默认 `config/dshbridge/http_token.txt`✗★；`-Ddshbridge.tokenFile=` / env `HTTP_TOKEN_FILE` 可覆盖） */
    static java.nio.file.Path httpTokenPath() {
        String p = ModConfig.TOKEN_FILE;
        if (p != null && !p.trim().isEmpty()) {
            return java.nio.file.Paths.get(p.trim());
        }
        return java.nio.file.Paths.get("config", "dshbridge", "http_token.txt");
    }

    /** 启动时生成/读取 token ✓（★文件坏了就重新生成✗★ —— 但绝不静默 ✓） */
    static void httpTokenLoadOrCreate() {
        java.nio.file.Path p = httpTokenPath();
        HTTP_TOKEN = "";
        HTTP_TOKEN_SRC = "none";
        try {
            if (java.nio.file.Files.isRegularFile(p)) {
                String t = new String(java.nio.file.Files.readAllBytes(p),
                        java.nio.charset.StandardCharsets.UTF_8).trim();
                if (t.matches("[0-9a-fA-F]{16,128}")) {
                    HTTP_TOKEN = t;
                    HTTP_TOKEN_SRC = "file";
                    return;
                }
                DshBridgeMod.httpEventServer( "token=regen reason=bad_content");
            }
            java.security.SecureRandom rnd = new java.security.SecureRandom();
            StringBuilder sb = new StringBuilder(32);
            for (int i = 0; i < 32; i++) {
                sb.append("0123456789abcdef".charAt(rnd.nextInt(16)));
            }
            java.nio.file.Path parent = p.toAbsolutePath().getParent();
            if (parent != null) {
                java.nio.file.Files.createDirectories(parent);
            }
            java.nio.file.Files.write(p, (sb + "\n").getBytes(java.nio.charset.StandardCharsets.UTF_8));
            HTTP_TOKEN = sb.toString();
            HTTP_TOKEN_SRC = "generated";
            DshBridgeMod.httpEventServer( "token=created path=" + p.toString().replace('\\', '/'));
        } catch (Exception exc) {
            // ★fail closed✗★：token 建不出来 ⇒ 写请求一律拒（宁可大声坏 ✗ 不可静默开着 ✓）
            HTTP_TOKEN = "";
            HTTP_TOKEN_SRC = "failed:" + exc.getClass().getSimpleName();
            DshBridgeMod.httpEventServer( "token=failed reason=" + exc.getClass().getSimpleName());
        }
    }

    static boolean httpTokenOk(String provided) {
        String t = HTTP_TOKEN;
        if (t == null || t.isEmpty()) {
            return false;                       // fail closed
        }
        return provided != null && provided.equals(t);
    }

    // ── /raw 白名单（★先 grep 全仓用法再收紧✗★）──────────────────────────────
    //   现成真用法（2026-11-02 grep）：
    //     · `player Bot spawn` / `player Bot spawn at x y z`（拉假人：这条不能走 /cmd，
    //        因为 /cmd 包的是 `execute as Bot` ⇒ 假人不在就跑不了 ✓）
    //     · `setblock x y z <block>` / `tp Bot x y z` / `item replace entity Bot hotbar.N with <item> <n>`
    //        （human_action_test.py --live 的现场准备 ✓）
    //     · `gamemode survival Bot`（拉回来后设生存 ✓）
    //   ★白名单外一律拒 ✗ 回执必须说清理由（`reason=not_whitelisted`）✓
    static final java.util.regex.Pattern RAW_ALLOW_PLAYER = java.util.regex.Pattern.compile(
            "^player ([A-Za-z0-9_]{1,16}) (spawn|kill)( .*)?$");
    static final java.util.regex.Pattern RAW_ALLOW_SETBLOCK = java.util.regex.Pattern.compile(
            "^setblock (-?[0-9]+) (-?[0-9]+) (-?[0-9]+) ([A-Za-z0-9_:.\\[\\]{},=/+\\-]+)$");
    static final java.util.regex.Pattern RAW_ALLOW_TP = java.util.regex.Pattern.compile(
            "^tp ([A-Za-z0-9_]{1,16}) (-?[0-9.]+) (-?[0-9.]+) (-?[0-9.]+)( [-0-9.]+ [-0-9.]+)?$");
    static final java.util.regex.Pattern RAW_ALLOW_ITEM = java.util.regex.Pattern.compile(
            "^item replace entity ([A-Za-z0-9_]{1,16}) hotbar\\.[0-8] with ([A-Za-z0-9_:.]+)( [0-9]{1,2})?$");
    static final java.util.regex.Pattern RAW_ALLOW_GAMEMODE = java.util.regex.Pattern.compile(
            "^gamemode (survival|creative|adventure|spectator) ([A-Za-z0-9_]{1,16})$");
    static final String RAW_ALLOWED_KINDS = "player,setblock,tp,item,gamemode";

    static boolean rawBotName(String n) {
        // ★79.534✗★：默认名走配置（默认仍是 "Bot" ✓）；WATCHED 仍允许（`/dshevents watch` 改过也兼容 ✓）
        return ModConfig.BOT_NAME.equals(n) || (n != null && n.equals(DshBridgeMod.WATCHED));
    }

    /** null ⇒ 放行 ✓ 非 null ⇒ 拒（值是 `reason=...`）✗ */
    static String rawDenyReason(String cmd) {
        String c = (cmd == null ? "" : cmd.trim()).replaceAll("\\s+", " ");
        java.util.regex.Matcher m = RAW_ALLOW_PLAYER.matcher(c);
        if (m.matches() && rawBotName(m.group(1))) {
            return null;
        }
        m = RAW_ALLOW_SETBLOCK.matcher(c);
        if (m.matches()) {
            return null;
        }
        m = RAW_ALLOW_TP.matcher(c);
        if (m.matches() && rawBotName(m.group(1))) {
            return null;
        }
        m = RAW_ALLOW_ITEM.matcher(c);
        if (m.matches() && rawBotName(m.group(1))) {
            return null;
        }
        m = RAW_ALLOW_GAMEMODE.matcher(c);
        if (m.matches() && rawBotName(m.group(2))) {
            return null;
        }
        return "reason=not_whitelisted";
    }

    static void httpLogReq(String reqId, String op, String status, long t0) {
        long ms = (System.nanoTime() - t0) / 1_000_000L;
        String line = "id=" + reqId + " op=" + op + " status=" + status + " ms=" + ms;
        synchronized (HTTP_REQS) {
            HTTP_REQS.addLast(line);
            while (HTTP_REQS.size() > HTTP_REQS_KEEP) {
                HTTP_REQS.removeFirst();
            }
        }
    }

    public static void httpStart(net.minecraft.server.MinecraftServer srv) {
        httpStop();
        httpTokenLoadOrCreate();
        try {
            java.net.ServerSocket ss = new java.net.ServerSocket();
            ss.setReuseAddress(true);
            ss.bind(new java.net.InetSocketAddress("127.0.0.1", HTTP_PORT));
            HTTP_SS = ss;
            HTTP_WORLD_LANE = java.util.concurrent.Executors.newSingleThreadExecutor(r -> {
                Thread t = new Thread(r, "dsh-world-lane");
                t.setDaemon(true);
                return t;
            });
            HTTP_POOL = new java.util.concurrent.ThreadPoolExecutor(
                    HTTP_WORKERS, HTTP_WORKERS, 30L, java.util.concurrent.TimeUnit.SECONDS,
                    new java.util.concurrent.LinkedBlockingQueue<>(64),
                    r -> {
                        Thread t = new Thread(r, "dsh-http-worker");
                        t.setDaemon(true);
                        return t;
                    },
                    new java.util.concurrent.ThreadPoolExecutor.AbortPolicy());
            Thread th = new Thread(() -> httpAcceptLoop(srv), "dsh-http-accept");
            th.setDaemon(true);
            th.start();
            HTTP_THREAD = th;
            DshBridgeMod.httpEventServer( "port=" + HTTP_PORT + " state=started workers=" + HTTP_WORKERS
                    + " pool_on=" + HTTP_POOL_ON + " token_src=" + HTTP_TOKEN_SRC);
        } catch (Exception exc) {
            DshBridgeMod.httpEventServer( "state=failed error=" + exc.getClass().getSimpleName());
        }
    }

    public static void httpStop() {
        try {
            if (HTTP_SS != null) {
                HTTP_SS.close();
            }
        } catch (Exception ignored) {
            // ★关不掉也不许静默✗★
            DshBridgeMod.httpEventServer( "state=close_error");
        }
        HTTP_SS = null;
        if (HTTP_POOL != null) {
            HTTP_POOL.shutdownNow();
            HTTP_POOL = null;
        }
        if (HTTP_WORLD_LANE != null) {
            HTTP_WORLD_LANE.shutdownNow();
            HTTP_WORLD_LANE = null;
        }
        HTTP_THREAD = null;
    }

    /** accept 线程：只收连接 ＋ 丢给线程池 ✓（★绝不在 accept 循环里跑命令✗★） */
    static void httpAcceptLoop(net.minecraft.server.MinecraftServer srv) {
        while (HTTP_SS != null && !HTTP_SS.isClosed()) {
            java.net.Socket sock;
            try {
                sock = HTTP_SS.accept();
            } catch (Exception exc) {
                if (HTTP_SS != null && !HTTP_SS.isClosed()) {
                    DshBridgeMod.httpEventError( String.valueOf(exc.getClass().getSimpleName()));
                }
                continue;
            }
            if (!HTTP_POOL_ON || HTTP_POOL == null) {
                // ★回滚模式✗★：旧行为 —— accept 线程内联处理（一个慢请求会堵住 /health）
                httpHandle(srv, sock);
                continue;
            }
            try {
                HTTP_POOL.execute(() -> httpHandle(srv, sock));
            } catch (java.util.concurrent.RejectedExecutionException rex) {
                try {
                    sock.close();
                } catch (Exception ignored) {
                    // ★连接已经废了也不许静默✗★
                }
                DshBridgeMod.httpEventError( "handler=queue_full");
            }
        }
    }

    /** 一个请求：★校验 → /health 就地回 → /cmd /raw 进世界车道 → 回执✗★ */
    static void httpHandle(net.minecraft.server.MinecraftServer srv, java.net.Socket s) {
        String reqId = "r" + HTTP_REQ_SEQ.incrementAndGet();
        long t0 = System.nanoTime();
        String op = "?";
        try (java.net.Socket sock = s) {
            sock.setSoTimeout(45000);
            java.io.InputStream is = sock.getInputStream();
            java.io.OutputStream os = sock.getOutputStream();
            java.io.BufferedReader br = new java.io.BufferedReader(
                    new java.io.InputStreamReader(is, java.nio.charset.StandardCharsets.UTF_8));
            String reqLine = br.readLine();
            if (reqLine == null) {
                return;
            }
            int contentLen = 0;
            String originHdr = null;
            String tokenHdr = null;
            String h;
            while ((h = br.readLine()) != null && !h.isEmpty()) {
                String low = h.toLowerCase(java.util.Locale.ROOT);
                if (low.startsWith("content-length:")) {
                    try {
                        contentLen = Integer.parseInt(low.substring(15).trim());
                    } catch (Exception ignored) {
                        contentLen = 0;
                    }
                } else if (low.startsWith("origin:")) {
                    originHdr = h.substring(7).trim();
                } else if (low.startsWith("x-dsh-token:")) {
                    tokenHdr = h.substring(12).trim();
                }
            }
            if (contentLen > HTTP_CONTENT_LIMIT) {
                httpReply(os, reqId, 413, "ERR:body_too_large reason=limit");
                httpLogReq(reqId, "?", "limit", t0);
                return;
            }
            StringBuilder body = new StringBuilder();
            for (int i = 0; i < contentLen; i++) {
                int c = br.read();
                if (c < 0) {
                    break;
                }
                body.append((char) c);
            }
            String cmd = body.toString().trim();
            HTTP_HITS.incrementAndGet();

            // ① CSRF：任何带 Origin 的请求一律拒（★所有端点✗★ —— 浏览器简单请求没有预检 ✗）
            if (originHdr != null) {
                httpReply(os, reqId, 403, "ERR:csrf reason=origin_header");
                httpLogReq(reqId, "?", "csrf", t0);
                return;
            }
            // ② /health：不需要 token ✓ ★就地（worker 线程）回 ✗ 绝不进世界车道 ✓
            if (reqLine.contains("/health")) {
                httpReply(os, reqId, 200, "ok dshbridge-http");
                return;
            }
            op = reqLine.contains("/raw") ? "raw" : "cmd";
            // ③ token：/cmd 与 /raw 必须带 X-DSH-Token（★/health 除外✗★）
            if (!httpTokenOk(tokenHdr)) {
                boolean missing = tokenHdr == null || tokenHdr.isEmpty();
                httpReply(os, reqId, 401, missing
                        ? "ERR:auth reason=missing_token"
                        : "ERR:auth reason=bad_token");
                httpLogReq(reqId, op, missing ? "auth_missing" : "auth_bad", t0);
                return;
            }
            if (cmd.isEmpty()) {
                httpReply(os, reqId, 200, "ERR:empty_command");
                httpLogReq(reqId, op, "empty", t0);
                return;
            }
            // ④ /raw 白名单
            if ("raw".equals(op)) {
                String deny = rawDenyReason(cmd);
                if (deny != null) {
                    httpReply(os, reqId, 403, "ERR:raw_denied " + deny);
                    httpLogReq(reqId, op, "raw_denied", t0);
                    return;
                }
            }
            // ⑤ 世界命令：★一条单线程车道 ⇒ 串行且保序 ✓ 绝不并行写世界✗★
            String resp = httpWorldLane(srv, reqId, op, cmd);
            httpReply(os, reqId, 200, resp);
            httpLogReq(reqId, op, resp.startsWith("ERR:") ? "err" : "ok", t0);
            if (reqLine.contains("/cmd")) {
                DshBridgeMod.LAST_CMD_TICK = srv.overworld() == null ? DshBridgeMod.LAST_CMD_TICK
                        : srv.overworld().getGameTime();
            }
        } catch (Exception exc) {
            DshBridgeMod.httpEventError( "handler=" + exc.getClass().getSimpleName());
        }
    }

    /** /cmd 与 /raw 的串行入口 ✓（单线程 executor ⇒ 世界写不并行、按到达顺序执行） */
    static String httpWorldLane(net.minecraft.server.MinecraftServer srv, String reqId,
                                String op, String cmd) {
        final java.util.concurrent.ExecutorService lane = HTTP_WORLD_LANE;
        if (lane == null) {
            return "ERR:no_lane reason=shutdown";
        }
        long t0 = System.nanoTime();
        java.util.concurrent.Future<String> f = lane.submit(() -> "raw".equals(op)
                ? httpRunRaw(srv, cmd, reqId)
                : httpRunCommand(srv, cmd, reqId));
        try {
            String r = f.get(HTTP_LANE_TIMEOUT_MS, java.util.concurrent.TimeUnit.MILLISECONDS);
            long ms = (System.nanoTime() - t0) / 1_000_000L;
            if (ms > HTTP_LANE_MS_MAX) {
                HTTP_LANE_MS_MAX = ms;
            }
            return r == null ? "ERR:null" : r;
        } catch (java.util.concurrent.TimeoutException te) {
            f.cancel(true);
            return "ERR:timeout reason=lane";
        } catch (java.util.concurrent.ExecutionException ee) {
            return "ERR:handler reason=" + ee.getCause().getClass().getSimpleName();
        } catch (InterruptedException ie) {
            Thread.currentThread().interrupt();
            return "ERR:interrupted";
        }
    }

    static void httpReply(java.io.OutputStream os, String reqId, int status, String resp)
            throws java.io.IOException {
        byte[] out = resp.getBytes(java.nio.charset.StandardCharsets.UTF_8);
        String reason = switch (status) {
            case 200 -> "OK";
            case 401 -> "Unauthorized";
            case 403 -> "Forbidden";
            case 413 -> "Payload Too Large";
            default -> "Error";
        };
        os.write(("HTTP/1.1 " + status + " " + reason + "\r\n"
                + "Content-Type: text/plain; charset=utf-8\r\n"
                + "Content-Length: " + out.length + "\r\n"
                + "X-DSH-Req: " + reqId + "\r\n"
                + "Connection: close\r\n\r\n").getBytes(java.nio.charset.StandardCharsets.UTF_8));
        os.write(out);
        os.flush();
    }

    /** /dshhttp —— 只读自报：并发/令牌/白名单状态（★绝不回 token 本身✗★） */
    static int httpDiag(CommandContext<CommandSourceStack> ctx) {
        int poolActive = -1;
        int poolQ = -1;
        if (HTTP_POOL != null) {
            poolActive = HTTP_POOL.getActiveCount();
            poolQ = HTTP_POOL.getQueue().size();
        }
        DshBridgeMod.ok(ctx.getSource(), "dshhttp port=" + HTTP_PORT
                + " pool=" + (HTTP_POOL_ON ? HTTP_WORKERS : 0) + " pool_on=" + HTTP_POOL_ON
                + " pool_active=" + poolActive + " pool_q=" + poolQ + " lane=1"
                + " token_file=" + httpTokenPath().toString().replace('\\', '/')
                + " token_len=" + (HTTP_TOKEN == null ? 0 : HTTP_TOKEN.length())
                + " token_header=X-DSH-Token token_src=" + HTTP_TOKEN_SRC
                + " hits=" + HTTP_HITS.get() + " reqs=" + HTTP_REQ_SEQ.get()
                + " lane_ms_max=" + HTTP_LANE_MS_MAX
                + " raw_allow=" + RAW_ALLOWED_KINDS);
        return 1;
    }

    /** /dshreqs —— 只读：最近请求账本（A7 让"事件 ↔ 请求"能对上） */
    static int httpReqs(CommandContext<CommandSourceStack> ctx, int n) {
        List<String> out = new ArrayList<>();
        synchronized (HTTP_REQS) {
            out.addAll(HTTP_REQS);
        }
        int show = Math.max(1, Math.min(n, out.size()));
        StringBuilder sb = new StringBuilder("dshreqs total=" + HTTP_REQ_SEQ.get() + " n=" + out.size());
        for (int i = Math.max(0, out.size() - show); i < out.size(); i++) {
            sb.append(" | ").append(out.get(i));
        }
        DshBridgeMod.ok(ctx.getSource(), sb.toString());
        return out.size();
    }


    /** ★★2.54.0✗★★：**服务器身份**跑一条命令（★不需要假人✗★）✗
     *  ★典型用途✗★：★player Bot spawn —— 拉假人这条命令本身不能依赖假人 ✓
     */
    static String httpRunRaw(net.minecraft.server.MinecraftServer srv, String cmd, String reqId) {
        java.util.List<String> out = java.util.Collections.synchronizedList(new java.util.ArrayList<>());
        java.util.concurrent.CountDownLatch done = new java.util.concurrent.CountDownLatch(1);
        srv.execute(() -> {
            DshBridgeMod.REQ_CTX.set(reqId);                 // ★A7✗★：这条命令里发的事件都带上同一个 req=
            try {
                final java.util.List<String> O = out;
                net.minecraft.commands.CommandSource sink = new net.minecraft.commands.CommandSource() {
                    @Override
                    public void sendSystemMessage(net.minecraft.network.chat.Component c) {
                        try {
                            O.add(c.getString());
                        } catch (Exception ignored) {
                            O.add("ERR:component");
                        }
                    }

                    @Override
                    public boolean acceptsSuccess() {
                        return true;
                    }

                    @Override
                    public boolean acceptsFailure() {
                        return true;
                    }

                    @Override
                    public boolean shouldInformAdmins() {
                        return false;
                    }
                };
                net.minecraft.server.level.ServerLevel lvl = srv.overworld();
                if (lvl == null) {
                    O.add("ERR:no_level");
                    return;
                }
                net.minecraft.commands.CommandSourceStack src =
                        new net.minecraft.commands.CommandSourceStack(sink,
                                net.minecraft.world.phys.Vec3.ZERO,
                                net.minecraft.world.phys.Vec2.ZERO, lvl, 4,
                                "dsh-raw", net.minecraft.network.chat.Component.literal("dsh-raw"),
                                srv, null);
                srv.getCommands().performPrefixedCommand(src, cmd);
            } catch (Exception exc) {
                out.add("ERR:" + exc.getClass().getSimpleName());
            } finally {
                DshBridgeMod.REQ_CTX.remove();
                done.countDown();
            }
        });
        try {
            if (!done.await(30, java.util.concurrent.TimeUnit.SECONDS)) {
                return "ERR:timeout";
            }
        } catch (InterruptedException ie) {
            Thread.currentThread().interrupt();
            return "ERR:interrupted";
        }
        StringBuilder sb = new StringBuilder();
        synchronized (out) {
            for (String s2 : out) {
                if (sb.length() > 0) {
                    sb.append('\n');
                }
                sb.append(s2);
            }
        }
        return sb.toString();
    }

    /** ★把指令**送回服务器线程**跑 ✗ 等它跑完 ✗ 回执一次性带回✗★ */
    static String httpRunCommand(net.minecraft.server.MinecraftServer srv, String cmd, String reqId) {
        java.util.List<String> out = java.util.Collections.synchronizedList(new java.util.ArrayList<>());
        java.util.concurrent.CountDownLatch done = new java.util.concurrent.CountDownLatch(1);
        srv.execute(() -> {
            DshBridgeMod.REQ_CTX.set(reqId);                 // ★A7✗★：这条命令里发的事件都带上同一个 req=
            try {
                net.minecraft.server.level.ServerPlayer bot = null;
                for (net.minecraft.server.level.ServerPlayer p : srv.getPlayerList().getPlayers()) {
                    if (p.getGameProfile().getName().equals(DshBridgeMod.WATCHED)) {
                        bot = p;
                        break;
                    }
                }
                if (bot == null) {
                    out.add("ERR:no_bot");
                    return;
                }
                final net.minecraft.server.level.ServerPlayer b = bot;
                // ★用**自定义 CommandSource** 收回执 ✗ 不依赖 withCallback 的签名（踩过 lambda 不兼容✗★）✗★
                net.minecraft.commands.CommandSource sink = new net.minecraft.commands.CommandSource() {
                    @Override
                    public void sendSystemMessage(net.minecraft.network.chat.Component c) {
                        try {
                            out.add(c.getString());
                        } catch (Exception ignored) {
                            // ★不许静默✗★
                            out.add("ERR:component");
                        }
                    }

                    @Override
                    public boolean acceptsSuccess() {
                        return true;
                    }

                    @Override
                    public boolean acceptsFailure() {
                        return true;
                    }

                    @Override
                    public boolean shouldInformAdmins() {
                        return false;
                    }
                };
                net.minecraft.commands.CommandSourceStack src =
                        new net.minecraft.commands.CommandSourceStack(sink, b.position(),
                                b.getRotationVector(), (net.minecraft.server.level.ServerLevel) b.level(),
                                4, "dsh-http", net.minecraft.network.chat.Component.literal("dsh-http"),
                                srv, b);
                String full = "execute as " + b.getGameProfile().getName() + " at @s run " + cmd;
                srv.getCommands().performPrefixedCommand(src, full);
            } catch (Exception exc) {
                out.add("ERR:" + exc.getClass().getSimpleName());
            } finally {
                DshBridgeMod.REQ_CTX.remove();
                done.countDown();
            }
        });
        try {
            if (!done.await(30, java.util.concurrent.TimeUnit.SECONDS)) {
                return "ERR:timeout";
            }
        } catch (InterruptedException ie) {
            Thread.currentThread().interrupt();
            return "ERR:interrupted";
        }
        StringBuilder sb = new StringBuilder();
        synchronized (out) {
            for (String s2 : out) {
                if (sb.length() > 0) {
                    sb.append('\n');
                }
                sb.append(s2);
            }
        }
        return sb.toString();
    }

}
