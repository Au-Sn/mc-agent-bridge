package com.dsh.bridge;

import com.mojang.brigadier.CommandDispatcher;
import com.mojang.brigadier.arguments.FloatArgumentType;
import com.mojang.brigadier.arguments.IntegerArgumentType;
import com.mojang.brigadier.arguments.StringArgumentType;
import com.mojang.brigadier.context.CommandContext;
import com.mojang.brigadier.exceptions.CommandSyntaxException;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.Commands;
import net.minecraft.commands.arguments.EntityArgument;
import net.minecraft.commands.arguments.coordinates.BlockPosArgument;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.level.EmptyBlockGetter;
import net.minecraft.world.level.block.LiquidBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.Container;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EquipmentSlot;
import net.minecraft.world.entity.item.ItemEntity;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.crafting.CraftingRecipe;
import net.minecraft.world.item.crafting.Ingredient;
import net.minecraft.world.item.crafting.Recipe;
import net.minecraft.world.item.crafting.RecipeType;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.EntityHitResult;
import net.minecraft.world.phys.HitResult;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;
import net.minecraftforge.common.capabilities.ForgeCapabilities;
import net.minecraftforge.event.RegisterCommandsEvent;
import net.minecraftforge.event.TickEvent;
import net.minecraftforge.eventbus.api.EventPriority;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.ModList;
import net.minecraftforge.fml.common.Mod;
import net.minecraftforge.items.IItemHandler;
import net.minecraftforge.items.wrapper.InvWrapper;
import net.minecraftforge.registries.ForgeRegistries;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

/**
 * dshbridge —— 让假人能干"真人能干的事"。
 *
 * <p>为什么必须写模组（三条都实测过 ✗ 见 docs/模组-容器存取与假人手.md）：
 * <ul>
 *   <li>原版 {@code /item replace block … container.N …} 只走原版 {@code Container} 接口 ✗
 *       ⇒ 对 {@code sophisticatedstorage:netherite_barrel} 这类**模组容器**直接报"不是容器" ✗</li>
 *   <li>KubeJS 的 {@code block.inventory} 只对原版容器稳 ✗ 且语义是"脚本替它搬"✗</li>
 *   <li>漏斗喂料只能**存**不能**取** ✗ 还要占一个漏斗 ✗</li>
 * </ul>
 *
 * <p>★ 假人与真人的**结构性差距**只有一个：**它没有客户端** ✗
 * ⇒ 一切"要靠客户端按键/界面/瞄准"的事它都做不了 ✗
 * ⇒ 本模组就是把那些事**搬回服务端**做一遍 ✓（语义与真人一致 ✓ 不白送东西 ✗）
 *
 * <p>四条设计纪律（都来自本项目最贵的教训 ✗）：
 * <ol>
 *   <li>一律走 {@code ForgeCapabilities.ITEM_HANDLER} ⇒ 原版 + 模组容器通吃 ✓</li>
 *   <li>**绝不静默吞物品** ✓：放不下就明确拒绝 ✓ 余量原样退回 ✓
 *       （KubeJS 版就因为在背包满时静默失败 ✗ 丢过铁锭与矿石 ✗）</li>
 *   <li>★**回执一律 ASCII**★ ✗（真实事故 ✓ 错题本 P13）：
 *       中文回执走 CC 命令通道回来会**全变成 {@code ?}** ✗
 *       ⇒ 智能体拿它当判据就会得到**静默假阳性** ✗✗
 *       ⇒ 所以本模组**所有**回执只用 ASCII ✓（中文解释写在注释里 ✓）</li>
 *   <li>★**要像真人就得有真人的约束**★ ✓：触及距离（4.5 格）**真的检查** ✗
 *       —— 隔着 8 格搬箱子"能成功"不是能力 ✓ 是能力膨胀 ✗</li>
 * </ol>
 */
@Mod("dshbridge")
public class DshBridgeMod {

    /** 真人（生存）的触及距离 ✓ 原版是 4.5 格 ✓ 这里照抄 ✓ */
    private static final double REACH = 4.5;
    /** 一次最多做多少份（防手滑把整箱材料做完 ✗） */
    private static final int MAX_TIMES = 64;

    // ══════════════════════════════════════════════════════════════════════════
    // ★v2.6 的常驻状态★（都只服务"让假人像真人一样动起来" ✓）
    // ══════════════════════════════════════════════════════════════════════════

    /** 事件流：**增量拉取** ✓（`/dshevents [since]` ✓）—— 有界 ✓ 不涨内存 ✓ */
    private static final ArrayDeque<String> EVENTS = new ArrayDeque<>();
    private static final AtomicLong EVENT_SEQ = new AtomicLong();
    private static final int EVENT_KEEP = 400;
    /** ★★2.56.0（A7）✗★★：当前 HTTP 请求 id（`r<N>`）✗
     *  ★只在这条请求的命令**在服务器线程执行时**设置✗★ ⇒ `ev()` 把 ` req=<id>` 追到事件行尾 ✓
     *  ⇒ ★哪条事件由哪次调用产生**可回放** ✓ 而 tick 里的事件不会被乱标（null ⇒ 不追加）✓
     */
    static final ThreadLocal<String> REQ_CTX = new ThreadLocal<>();

    /** 上一次"任何模组指令"发生在哪个 tick ✓（空闲看四周要避开"正在干活"✗ 见 AUTO_IDLE ✓） */
    static volatile long LAST_CMD_TICK = 0L;

    /** 正在走的玩家 ✓（一个玩家一份任务 ✓ 完成后留 30 秒给 `/dshwalk` 读结果 ✓） */
    private static final Map<UUID, WalkTask> WALKS = new ConcurrentHashMap<>();

    private static final AtomicLong TICK_COUNT = new AtomicLong();

    /** 被观测的玩家名 ✓（★79.534：默认仍 `Bot` ✗ 但可用 `-Ddshbridge.bot=` / env `BOT_NAME` 覆盖✓★） */
    static volatile String WATCHED = ModConfig.BOT_NAME;

    /** 自动进食 ✗ 默认**关** ✓（要开就说一声 ✓：`/dshauto eat on` ✓） */
    private static volatile boolean AUTO_EAT = false;
    private static volatile int AUTO_EAT_MIN = 14;

    /** ★空闲四处看 ✗ 默认**关**★ ✓ —— 为什么默认关 ✗（这条很关键 ✓）：
     *  它靠的是"**最近没有指令**"来判定"空闲" ✗ 可筛矿那条路是
     *  Lua 里的 `use interval 1` **循环 12 秒不发指令** ✗
     *  ⇒ 看四周会**把准星转走** ✗ ⇒ 命中面从 `up` 变成别的 ✗
     *  ⇒ 而 P16 说得明明白白：**打错面时一声不响、完全无效** ✗✗
     *  ⇒ 那就等于"人感"把"筛矿"变成静默失败 ✗ —— 这种交换绝不接受 ✗
     *  ⇒ 所以：**默认关 ✓ 要示人时手动开一句** ✓（`/dshauto idle on` ✓）
     */
    private static volatile boolean AUTO_IDLE = false;

    // ══════════════════════════════════════════════════════════════════════════
    // ★★v2.8：拟人化 —— **会听 ✓ 会说 ✓ 会自己溜达两下**★★（用户点的优先级 ✓）
    //   用户原话 ✓：「所需的**对话**，和一定的**自行移动**等拟人化行为，优先做一下这些」✓
    //
    //   设计原则（都是本项目踩出来的 ✓）：
    //     · ★绝不干扰"判据的支点"★ ✗（准星 ✓ 站位 ✓ 手持 ✓ —— 见 P25 ✓）
    //       ⇒ 一切拟人行为都挂在一个**总门槛**后面 ✓：**最近 15 秒内没有任何模组指令** ✓
    //         （主线作业每秒都在发指令 ✓ ⇒ 干活时它**绝不会**自作主张 ✓✓）
    //     · ★只在自己的小圈子里活动★ ✗（半径默认 4 格 ✓ 而且先验"那一格站得下人"✓）
    //       —— 空岛乱走 = 掉虚空 ✗ 这条底线不放松 ✓
    //     · ★会听但要**能过 CC 通道**★ ✗：聊天内容里的非 ASCII 一律转义成 `U+XXXX` ✓
    //       （中文过 CC 命令通道会变 `?` ✗ 见 P13 ✓ —— 转义后**信息一点不丢** ✓ 且判据全 ASCII ✓）
    // ══════════════════════════════════════════════════════════════════════════

    /** 拟人化总开关 ✓（默认**开** ✓ —— 用户明确要求 ✓；`/dshidle off` 可关 ✓） */
    private static volatile boolean HUMANOID = true;
    /** ★canned 快嘴开关★ ✗（v2.11.1 ✓）—— 用户抓到的**第三条**真错误的核心 ✓：
     *  `talk.py` 的 `keep_quiet()` 每 10 秒发一条保活探针（目的是让模组这句 canned 让位 ✓ 好让 LLM 当唯一声音 ✓）
     *  而**任何** `dsh*` 指令的回执都会刷新 `LAST_CMD_TICK` ✓（`ok()`/`bad()` 里 ✓）
     *  ⇒ `isQuiet()` 要的"安静 300 tick"**永远达不到** ✗ ⇒ **v2.11 的反应一句都不会响** ✗✗
     *  ⇒ 正解 ✓：**别再靠"顶掉安静门槛"来让位** ✗ 而是给 canned 一张**自己的开关** ✓
     *     （`/dshquiet canned=off` ✓）—— 于是"安静"重新等于"真的没人指挥它" ✓ 反应就能响了 ✓ */
    private static volatile boolean CANNED = true;
    /** 溜达半径 ✓（小步 ✓ 不离开这片平台 ✓） */
    private static volatile int HUMANOID_RADIUS = 4;
    /** 总门槛：最近一次模组指令之后要安静这么多 tick 才允许自作主张 ✓（15 秒 ✓） */
    private static final long HUMANOID_QUIET_TICKS = 300;
    /** 锚点：开拟人化时它站的地方 ✓（溜达不许离锚点太远 ✓ 空岛安全 ✓） */
    private static double anchorX = Double.NaN, anchorY = Double.NaN, anchorZ = Double.NaN;
    /** 各种节流与计数 ✓（都要能**如实报出来** ✗ 不许藏着 ✓） */
    private static long lastStrollTick = 0, lastGlanceTick = 0, lastLineTick = 0;
    private static int nGlance = 0, nStroll = 0, nLine = 0, nHeard = 0, nReply = 0, nGreet = 0;
    private static final Map<UUID, Long> greetedAt = new ConcurrentHashMap<>();
    /** 偶尔自语的短句 ✓（很短 ✓ 很稀 ✓ —— 不刷屏 ✗） */
    private static final String[] SELF_LINES = {
            "这地方风有点大。", "再把筛子理一理。", "嗯，种子还够。", "该收的应该快熟了。",
    };
    /** 被叫到名字时的回话 ✓（很短 ✓ 而且**一次一句** ✓ 带节流 ✓） */
    private static final String[] REPLY_LINES = {
            "在。", "哎，我在。", "怎么了？", "听着呢。",
    };
    /** 打招呼 ✓（玩家走近时一次 ✓ 60 秒内不重复 ✓） */
    private static final String[] GREET_LINES = {
            "你好。", "来了？", "早。",
    };

    /** 观测状态（每 10 tick 跟一次 ✓ 只存"上一次的值" ✓ 便宜 ✓） */
    private static double wHp = -1, wFood = -1, wX = Double.NaN, wZ = Double.NaN, wY = Double.NaN;
    private static int wInv = -1, wSel = -1, wXp = -1;
    private static String wMode = "", wHeld = "";
    private static final Map<Integer, Integer> wDropWarned = new ConcurrentHashMap<>();

    public DshBridgeMod() {
    }

    @Mod.EventBusSubscriber(modid = "dshbridge")
    public static class Events {
        @SubscribeEvent
        public static void onRegisterCommands(RegisterCommandsEvent event) {
            register(event.getDispatcher());
        }

        /** ★v2.6：逐 tick 行为都挂在这里★ ✓
         *
         * <p>为什么必须逐 tick ✗（而不是"再来一条指令"✗）：
         * 走路 = 每 tick 给一次移动输入 ✓（真人按住 W 就是这样 ✓）
         * ⇒ 一条指令管一整段 ✓ 而不是"一格一条指令"✗（那正是慢与抖的根源 ✗）
         */
    @SubscribeEvent
    public static void onServerStarted(net.minecraftforge.event.server.ServerStartedEvent e) {
        HttpBridge.httpStart(e.getServer());
    }

    @SubscribeEvent
    public static void onServerStopping(net.minecraftforge.event.server.ServerStoppingEvent e) {
        HttpBridge.httpStop();
    }

        @SubscribeEvent
        public static void onPlayerTick(TickEvent.PlayerTickEvent e) {
            if (e.phase == TickEvent.Phase.END) {
                // ★2.49.0✗★：★tick 末尾重申转身朝向（★写得比外部写者晚✗★）
                if (e.player instanceof ServerPlayer p) {
                    bracket(p, "player_end_before");
                    reassertTurn(p);
                    bracket(p, "player_end_after");
                    // ★2.56.0✗★：**按玩家**存"上一 tick 结束时的 yaw"（★别和别人的比✗★）
                    PREV_END_YAW_BY.put(p.getUUID(), (double) p.getYRot());
                }
                return;
            }
            if (e.phase != TickEvent.Phase.START) {
                return;
            }
            if (e.player instanceof ServerPlayer p) {
                bracket(p, "player_start");
                double y0 = p.getYRot();
                // ★跨 tick 对照✗★：同一个人上一 tick 结束值 ≠ 本 tick 开始值 ⇒ 写发生在**我们处理之外**
                Double prevEnd = PREV_END_YAW_BY.get(p.getUUID());
                if (prevEnd != null && Math.abs(y0 - prevEnd) > 0.01) {
                    YAW_WRITES++;
                    YAW_EXTERNAL++;
                    YAW_LAST = "external " + String.format("%.1f", prevEnd)
                            + "->" + String.format("%.1f", y0);
                    ev("yaw_write", "handler=external who=" + esc(p.getGameProfile().getName())
                            + " prev_end=" + String.format("%.1f", prevEnd)
                            + " tick_start=" + String.format("%.1f", y0));
                }
                tickTurn(p);        // ★2.46.0✗★ 平滑转身 ＋ yaw 轨迹（★只改朝向✗★）
                probeYaw(p, "tickTurn", y0);
                double y1 = p.getYRot();
                tickWalk(p);
                probeYaw(p, "tickWalk", y1);
                double y2 = p.getYRot();
                tickDo(p);          // ★★v2.26✗★ 动作队列（★实时世界判每步✗★）✗★
                probeYaw(p, "tickDo", y2);
                double y3 = p.getYRot();
                tickAuto(p);
                probeYaw(p, "tickAuto", y3);
                bracket(p, "after_auto");
                PREV_END_YAW_BY.put(p.getUUID(), (double) p.getYRot());
            }
        }

        /** ★★v2.8：**听**★★ ✓ —— 把玩家聊天记进事件流 ✓ 并在被叫名字时**抬头回一句** ✓
         *
         * <p>为什么要"听" ✗：用户要的是**对话** ✓ 而 v2.8 之前假人只会"说"✗（`dshsay` ✓）
         * ⇒ 别人跟它说话它**完全不知道** ✗ ⇒ 那不叫对话 ✓ 那叫广播 ✗
         *
         * <p>两条纪律都在这里落地 ✓：
         * <ol>
         *   <li>★非 ASCII 一律转义成 `\U+XXXX`★ ✗ —— 中文过 CC 命令通道会变 `?` ✗（P13 ✓）
         *       转义后**信息一点不丢** ✓ 而且智能体那侧判据仍然全 ASCII ✓</li>
         *   <li>★回话带节流 ＋ 只在"没人指挥它"时回★ ✗ —— 绝不抢话 ✗ 绝不刷屏 ✗</li>
         * </ol>
         */
        @SubscribeEvent
        public static void onChat(net.minecraftforge.event.ServerChatEvent e) {
            try {
                String who = e.getUsername() == null ? "?" : e.getUsername();
                String msg = e.getRawText() == null ? "" : e.getRawText();
                nHeard++;
                ev("chat", "who=" + esc(who) + " len=" + msg.length() + " msg=" + esc(msg));
                ServerPlayer p = e.getPlayer();
                // 被叫到名字 ⇒ 抬头看说话的人 ✓ 并回一句短话 ✓（20 秒内不重复 ✓ 正在干活时不掺和 ✓）
                String low = msg.toLowerCase();
                boolean called = low.contains(WATCHED.toLowerCase()) || low.contains("bot");
                long now = p != null ? lvl(p).getGameTime() : 0;
                if (p != null && called && now - lastLineTick > 400 && isQuiet(now) && CANNED) {
                    aimAt(p, e.getPlayer() == null ? p.position() : p.position());
                    sayAs(p, REPLY_LINES[(int) (Math.random() * REPLY_LINES.length)]);
                    nReply++;
                    lastLineTick = now;
                    ev("auto_reply", "to=" + esc(who) + " n=" + nReply);
                }
            } catch (Exception ignored) {
                // 听聊天出问题**绝不许影响游戏** ✓（观测是我们的事 ✗ 不是服务器的事 ✓）
            }
        }

        /** ★★v2.18：死亡保险 —— 只对**我们那个身体**生效★★ ✗
         *
         * <p>为什么要有它 ✗：用户那句「给 bot 上一个死亡不掉落」指的洞**真实存在** ✓ ——
         * 现有的墓碑机制在**掉虚空**时兜不住（★墓碑生成在死亡点 ⇒ 也在虚空里 ⇒ 取不回✗★ ✓）。
         *
         * <p>为什么**不**直接开全局 `keepInventory` ✗：
         * <ol>
         *   <li>那是**世界级**的 ⇒ 会改**玩家自己的**游戏 ✓（用户明确"先挂起"✗）</li>
         *   <li>★它会让**失败不可见**✗★：假人可以一次次走下岛、每次都不丢东西 ⇒ 账面全绿 ⇒
         *       可它是**坏掉的身体** ✗ —— 同族：**P17** 创造模式"死亡不掉落"让自给证据失真 ✓</li>
         * </ol>
         *
         * <p>⇒ 口径 ✓：**保险（这里 ✓）＋ 计数器（`bot_died` 事件数必须为 0 ✓）两条并行** ✗
         */
        @SubscribeEvent
        public static void onLivingDeath(net.minecraftforge.event.entity.living.LivingDeathEvent e) {
            boolean mine = false;
            try {
                if (!(e.getEntity() instanceof ServerPlayer p)) {
                    return;
                }
                if (!p.getName().getString().equals(WATCHED)) {
                    return;                       // ★只管我们那一个身体✗★（别动玩家的死亡 ✓）
                }
                mine = true;
                // ★★v2.18.2：**进入就先落一条证据**✗★★
                //   为什么 ✗（2026-10-01 实测教训 ✓）：v2.18 只在**搬完之后**发事件 ✓
                //     ⇒ 一旦在它之前抛异常 ⇒ `catch` **静默吞掉** ✗ ⇒
                //     ★外面看到的，与"这个事件压根没触发"**一模一样**✗★ ⇒ 诊断当场卡死 ✓
                //   （本次实测现场 ✓：`/kill` 一个 Carpet 假人**不走正常死亡**✗★
                //     —— `carpet.patches.EntityPlayerMPFake` 覆盖了 `kill(Component)` ✓
                //     它是"直接断开" ⇒ 不掉落 ✓ 不触发 `LivingDeathEvent` ✓
                //     而我没法区分"没触发"与"触发了但炸了" ✗）
                //   ⇒ 口径 ✓：**进入**先说一声 ✓ **搬完**再说一声 ✓
                //     两句都带 `phase=` ✗ ⇒ ★判据只认 `phase=stashed` 那句✗★
                ev("bot_died", "phase=enter who=" + esc(WATCHED)
                        + " pos=" + String.format("%.1f,%.1f,%.1f", p.getX(), p.getY(), p.getZ()));
                ServerLevel lv = lvl(p);
                var inv = p.getInventory();
                net.minecraft.nbt.ListTag items = new net.minecraft.nbt.ListTag();
                inv.save(items);
                int kept = 0;
                for (int i = 0; i < inv.getContainerSize(); i++) {
                    if (!inv.getItem(i).isEmpty()) {
                        kept += inv.getItem(i).getCount();
                    }
                }
                // ★先搬走、再清空✗★ —— 不然墓碑存一份 ＋ 我们还一份 ⇒ **凭空多一份** ✗（复制 bug ✓）
                inv.clearContent();
                net.minecraft.nbt.CompoundTag tag = new net.minecraft.nbt.CompoundTag();
                tag.putString("name", WATCHED);
                tag.put("items", items);
                double[] sp = LAST_SAFE.get(WATCHED);
                tag.putBoolean("has_pos", sp != null);
                if (sp != null) {
                    tag.putDouble("x", sp[0]);
                    tag.putDouble("y", sp[1]);
                    tag.putDouble("z", sp[2]);
                }
                tag.putLong("tick", lv.getGameTime());
                STASH = tag;
                stashSave();
                ev("bot_died", "phase=stashed who=" + esc(WATCHED) + " kept_items=" + kept
                        + " pos=" + String.format("%.1f,%.1f,%.1f", p.getX(), p.getY(), p.getZ())
                        + " safe=" + (sp == null ? "none"
                        : String.format("%.0f,%.0f,%.0f", sp[0], sp[1], sp[2])));
            } catch (Throwable ex) {
                // ★★v2.18.2：**不许静默**✗★★（"让失败大声" ✓ 本项目铁律 ✓）
                //   v2.18 这里写的是 `catch (Exception ignored)` ✗ —— ★那正是本项目最恨的形状✗★
                //   ⇒ 现在**双通道留痕** ✓：`latest.log`（人读 ✓ 全 ASCII ✓）＋ 事件流（判据读 ✓）
                String msg = esc(ex.getClass().getSimpleName() + ": " + ex.getMessage());
                System.out.println("[dshbridge] death-insurance FAILED at="
                        + (mine ? "stash" : "enter") + " -> " + msg);
                if (mine) {
                    ev("bot_died", "phase=error at=stash msg=" + msg);
                }
            }
        }

        /** 服务端 tick：低频（每 10 tick）做"值得记一笔"的观测 ✓ 便宜 ✓ */
        @SubscribeEvent(priority = EventPriority.LOWEST)
        public static void onServerTick(TickEvent.ServerTickEvent e) {
            if (e.phase != TickEvent.Phase.END) {
                // START：打一戳（★本 tick 开始时的朝向✗★）
                try {
                    if (e.getServer() != null) {
                        for (ServerPlayer pl : e.getServer().getPlayerList().getPlayers()) {
                            bracket(pl, "server_start");
                        }
                    }
                } catch (Exception exc) {          // ★不许静默✗★
                    ev("yaw_bracket", "at=server_exception");
                }
                return;
            }
            // ★★★2.56.0（N3 修）✗★★：holdYaw 原来写在 **START** 分支里 ✗
            //   （注释写的是"ServerTickEvent.END / 所有玩家 tick 之后" ✗ 两句**不一致** ✗ 实测抓到的）
            //   ⇒ 现在真的放在 **END**：所有 PlayerTick（turn→walk→do→auto）之后 ✓
            //   ⇒ ★tick 顺序没变✗★：四段仍在 onPlayerTick 里，hold 仍在它们**之后** ✓
            try {
                for (ServerPlayer pl : e.getServer() == null ? java.util.List.<ServerPlayer>of()
                        : e.getServer().getPlayerList().getPlayers()) {
                    holdYaw(pl);
                    bracket(pl, "server_end_after_hold");
                }
            } catch (Exception exc) {          // ★不许静默✗★
                ev("turn_hold", "reason=exception");
            }
            // ★★围栏要跑在**每一个 tick**✗★★（2026-10-03 ✓ 欠账 ⑰ ✓）：
            //   ★下面那个 `%10` 的门是给"观测"用的 ✗ 而围栏要拦的是**每 tick 的运动**✗★
            //   ⇒ ★口径✗★：★被拦的东西多快 ✗ 围栏就得多快✗★ ✓（★§79.40 那句"同频"✓★）
            if (LEASH_ON) {
                try {
                    leashTick(e.getServer());
                } catch (Throwable ignored) {
                    // ★围栏坏了也**绝不许**影响游戏 ✓（★但下一次 `dshleash status` 会看得出来✓★）
                }
            }
            if (TICK_COUNT.incrementAndGet() % 10 != 0) {
                return;
            }
            try {
                var server = e.getServer();
                var p = server.getPlayerList().getPlayerByName(WATCHED);
                stashEnsure();                 // ★v2.18：把上次"扣下的那一包"读回来 ✗（懒加载 ✓ 同皮肤那套 ✓）
                if (p != null) {
                    tickWatch(p);
                    rememberSafeSpot(p);       // ★v2.18：记"上一次站在内陆格"✗（送回平台要用它 ✓）
                    tryRestore(p);             // ★v2.18：它回来了 ⇒ 背包还回去 ＋ 送回安全落脚点 ✓
                }
            } catch (Exception ignored) {
                // 观测失败**绝不许影响游戏** ✓（观测是我们的事 ✗ 不是服务器的事 ✓）
            }
        }
    }

    private static void register(CommandDispatcher<CommandSourceStack> d) {
        final int PERM = 2;   // 与桥接的 cmd0 权限一致

        // ── /dshbox —— 容器存取（原版 ✓ 与模组 ✓ 通吃）────────────────────────
        d.register(Commands.literal("dshbox").requires(s -> s.hasPermission(PERM))
                .then(Commands.literal("peek")
                        .then(Commands.argument("pos", BlockPosArgument.blockPos())
                                .executes(ctx -> peek(ctx, 1))
                                .then(Commands.argument("page", IntegerArgumentType.integer(1))
                                        .executes(ctx -> peek(ctx, IntegerArgumentType.getInteger(ctx, "page"))))))
                .then(Commands.literal("take")
                        .then(Commands.argument("pos", BlockPosArgument.blockPos())
                                .executes(ctx -> take(ctx, "", Integer.MAX_VALUE))
                                .then(Commands.argument("item", StringArgumentType.string())
                                        .executes(ctx -> take(ctx, StringArgumentType.getString(ctx, "item"), Integer.MAX_VALUE))
                                        .then(Commands.argument("count", IntegerArgumentType.integer(1))
                                                .executes(ctx -> take(ctx, StringArgumentType.getString(ctx, "item"),
                                                        IntegerArgumentType.getInteger(ctx, "count")))))))
                .then(Commands.literal("put")
                        .then(Commands.argument("pos", BlockPosArgument.blockPos())
                                .executes(ctx -> put(ctx, "", Integer.MAX_VALUE))
                                .then(Commands.argument("item", StringArgumentType.string())
                                        .executes(ctx -> put(ctx, StringArgumentType.getString(ctx, "item"), Integer.MAX_VALUE))
                                        .then(Commands.argument("count", IntegerArgumentType.integer(1))
                                                .executes(ctx -> put(ctx, StringArgumentType.getString(ctx, "item"),
                                                        IntegerArgumentType.getInteger(ctx, "count"))))))));

        // ── /dshslot —— ★按槽位精确读写★（v2.1 ✓）────────────────────────────
        // 为什么需要 ✗：v2.0 的 take/put 只能按"**物品名子串**"匹配 ✓
        //   ⇒ 同一个物品占了多格（非常常见 ✗）时**分不清是哪一格** ✗
        //   ⇒ 而自动化经常要"就动第 0 格"✓（机器输入槽 ✓ 燃料槽 ✗）
        d.register(Commands.literal("dshslot").requires(s -> s.hasPermission(PERM))
                .then(Commands.literal("get")
                        .then(Commands.argument("pos", BlockPosArgument.blockPos())
                                .then(Commands.argument("slot", IntegerArgumentType.integer(0))
                                        .executes(ctx -> slotGet(ctx)))))
                .then(Commands.literal("take")
                        .then(Commands.argument("pos", BlockPosArgument.blockPos())
                                .then(Commands.argument("slot", IntegerArgumentType.integer(0))
                                        .executes(ctx -> slotTake(ctx, Integer.MAX_VALUE))
                                        .then(Commands.argument("count", IntegerArgumentType.integer(1))
                                                .executes(ctx -> slotTake(ctx, IntegerArgumentType.getInteger(ctx, "count")))))))
                .then(Commands.literal("put")
                        .then(Commands.argument("pos", BlockPosArgument.blockPos())
                                .then(Commands.argument("slot", IntegerArgumentType.integer(0))
                                        .executes(ctx -> slotPut(ctx, Integer.MAX_VALUE))
                                        .then(Commands.argument("count", IntegerArgumentType.integer(1))
                                                .executes(ctx -> slotPut(ctx, IntegerArgumentType.getInteger(ctx, "count"))))))));

        // ── /dshentbox —— ★实体容器★（箱子矿车 ✓ 漏斗矿车 ✓ v2.1 ✓）──────────
        d.register(Commands.literal("dshentbox").requires(s -> s.hasPermission(PERM))
                .then(Commands.literal("peek")
                        .then(Commands.argument("target", EntityArgument.entity())
                                .executes(ctx -> entBoxPeek(ctx, 1))
                                .then(Commands.argument("page", IntegerArgumentType.integer(1))
                                        .executes(ctx -> entBoxPeek(ctx, IntegerArgumentType.getInteger(ctx, "page"))))))
                .then(Commands.literal("take")
                        .then(Commands.argument("target", EntityArgument.entity())
                                .executes(ctx -> entBoxTake(ctx, "", Integer.MAX_VALUE))
                                .then(Commands.argument("item", StringArgumentType.string())
                                        .executes(ctx -> entBoxTake(ctx, StringArgumentType.getString(ctx, "item"), Integer.MAX_VALUE))
                                        .then(Commands.argument("count", IntegerArgumentType.integer(1))
                                                .executes(ctx -> entBoxTake(ctx, StringArgumentType.getString(ctx, "item"),
                                                        IntegerArgumentType.getInteger(ctx, "count")))))))
                .then(Commands.literal("put")
                        .then(Commands.argument("target", EntityArgument.entity())
                                .executes(ctx -> entBoxPut(ctx, "", Integer.MAX_VALUE))
                                .then(Commands.argument("item", StringArgumentType.string())
                                        .executes(ctx -> entBoxPut(ctx, StringArgumentType.getString(ctx, "item"), Integer.MAX_VALUE))
                                        .then(Commands.argument("count", IntegerArgumentType.integer(1))
                                                .executes(ctx -> entBoxPut(ctx, StringArgumentType.getString(ctx, "item"),
                                                        IntegerArgumentType.getInteger(ctx, "count"))))))));

        // ── /dshtrade —— ★跟村民交易★（真人点交易界面 ✗ 假人打不开 ✓ 这里补上）──
        // 走的是原版那条路 ✓：`interactOn` 打开商人菜单 ⇒ `setSelectionHint` ＋ `tryMoveItems`
        // （与服务端处理 `ServerboundSelectTradePacket` 时**同一套调用** ✓✓ 语义完全一致 ✓）
        d.register(Commands.literal("dshtrade").requires(s -> s.hasPermission(PERM))
                .then(Commands.literal("list")
                        .then(Commands.argument("target", EntityArgument.entity())
                                .executes(ctx -> tradeList(ctx))))
                .then(Commands.literal("do")
                        .then(Commands.argument("target", EntityArgument.entity())
                                .then(Commands.argument("index", IntegerArgumentType.integer(0))
                                        .executes(ctx -> tradeDo(ctx, 1))
                                        .then(Commands.argument("times", IntegerArgumentType.integer(1, MAX_TIMES))
                                                .executes(ctx -> tradeDo(ctx, IntegerArgumentType.getInteger(ctx, "times"))))))));

        // ── /dshsay ＋ /dshstats —— ★把 cc0 那两个 AP 外设的活儿接过来★（v2.2 ✓）──
        // 背景 ✓：用户定的方向是「**慢慢用模组去替代掉 CC 电脑的作用**」✗
        //   cc0 干的事里，这两件原来是它的外设在做 ✗：
        //     * `chatBox`          ⇒ 用 `/dshsay` 取代 ✓（走的是 `ServerPlayer#chat`
        //                             ⇒ **就是真人发消息那条路** ✓ 连聊天签名/前缀都一致 ✓）
        //     * `playerDetector`   ⇒ 用 `/dshstats` 取代 ✓（自己报位置/血量/饥饿/等级/模式 ✓）
        //   ⚠ 而"读方块 / 扫地形 / 管物品栏"那几件 ✓ 早已由 **cmd0 的桥接动作**覆盖 ✓
        //     （`block_state` ✓ `survey` ✓ `crosshair` ✓）＋ 本模组的 `dshbox`/`dshinv` ✓✓
        d.register(Commands.literal("dshsay").requires(s -> s.hasPermission(PERM))
                .then(Commands.argument("text", StringArgumentType.greedyString())
                        .executes(ctx -> {
                            CommandSourceStack src = ctx.getSource();
                            ServerPlayer p = src.getPlayerOrException();
                            String raw = StringArgumentType.getString(ctx, "text");
                            // ★★v2.8.2：出口先**解转义**★★ ✗
                            //   实测 ✓：智能体送中文过来 ⇒ 聊天里是 `ä½ å¥½…` ✗
                            //   （UTF-8 被当单字节又编码了一次 ✗ —— 坏在 网关→CC→commands.exec 那一趟 ✓）
                            //   ⇒ 修法与事件流对称 ✓：外面只发**纯 ASCII** 的 `U+XXXX` ✓ 这里解回来 ✓
                            String msg = unesc(raw);
                            // ★ 真人发消息是**客户端签名**的 ✗ 假人没有客户端 ⇒ **做不到 1:1** ✗
                            //   （1.20.1 起聊天要签名 ✓ `ServerPlayer#chat` 这个便利方法已经没了 ✗
                            //     —— 我第一版就是写 `p.chat(msg)` ✗ 被编译器当场挡下 ✓）
                            //   ⇒ 退而求其次 ✓：广播一条带 `<名字>` 前缀的普通消息 ✓
                            //     别人看到的形状与聊天一致 ✓ 但它**不是**签名聊天 ✓ 注释里说清 ✓
                            var server = src.getServer();
                            server.getPlayerList().broadcastSystemMessage(
                                    Component.literal("<" + p.getName().getString() + "> " + msg), false);
                            ok(src, "dshsay sent chars=" + msg.length() + " raw=" + raw.length()
                                    + " unescaped=" + (unesc(raw).length() != raw.length()));
                            return msg.length();
                        })));

        // ── /dshidle —— ★拟人化★（v2.8 ✓ 会听 ✓ 会说 ✓ 会自己溜达 ✓ 用户点名要的 ✓）──
        // 用法：/dshidle status | on | off | radius <n>
        //   ⚠ 总门槛 ✓：**最近 15 秒内没有任何模组指令**它才自作主张 ✓
        //     （主线作业每秒都在发指令 ⇒ 干活时它**绝不会**乱动 ✓ 见 P25 ✓）
        // ★v2.11.1：安静探针（**不刷新** LAST_CMD_TICK ✓）＋ canned 快嘴开关 ✓
        //   —— 用户发现"保活探针把 isQuiet 顶死 ⇒ 反应永远不响"之后加的 ✓
        // ★v2.12.0：皮肤（一个贪心参数 ✓ 通用性见 docs/模组-皮肤系统.md ✓）
        d.register(Commands.literal("dskskin").requires(s -> s.hasPermission(PERM))
                .executes(ctx -> skinCmd(ctx, ""))
                .then(Commands.argument("args", StringArgumentType.greedyString())
                        .executes(ctx -> skinCmd(ctx, StringArgumentType.getString(ctx, "args")))));
        // ★v2.13：掉落物列表（含 in_water ✓）—— 判据 D1 靠它 ✓
        d.register(Commands.literal("dshdrop").requires(s -> s.hasPermission(PERM))
                .executes(ctx -> dropList(ctx, 8.0))
                .then(Commands.argument("radius", FloatArgumentType.floatArg(1.0f, 48.0f))
                        .executes(ctx -> dropList(ctx,
                                FloatArgumentType.getFloat(ctx, "radius")))));
        d.register(Commands.literal("dshquiet").requires(s -> s.hasPermission(PERM))
                .executes(DshBridgeMod::quietProbe)
                .then(Commands.literal("canned")
                        .then(Commands.literal("on").executes(ctx -> quietCanned(ctx, true)))
                        .then(Commands.literal("off").executes(ctx -> quietCanned(ctx, false)))));
        d.register(Commands.literal("dshidle").requires(s -> s.hasPermission(PERM))
                .executes(ctx -> idleCmd(ctx, "status", 0))
                .then(Commands.literal("status").executes(ctx -> idleCmd(ctx, "status", 0)))
                .then(Commands.literal("on").executes(ctx -> idleCmd(ctx, "on", 0)))
                .then(Commands.literal("off").executes(ctx -> idleCmd(ctx, "off", 0)))
                .then(Commands.literal("radius")
                        .then(Commands.argument("n", IntegerArgumentType.integer(1, 16))
                                .executes(ctx -> idleCmd(ctx, "radius",
                                        IntegerArgumentType.getInteger(ctx, "n"))))));

        // ── /dshequip —— ★按名字把任意物品换到手上★（v2.7 ✓ 修的是 P29 那一整类 ✗）──────
        d.register(Commands.literal("dshequip").requires(s -> s.hasPermission(PERM))
                .then(Commands.argument("item", StringArgumentType.string())
                        .executes(ctx -> equip(ctx))));

        // ── /dshplace —— ★显式放方块 ＋ 落点校验★（v2.7 ✓ 修的是 P30 那个"FAIL 不说原因"✗）──
        // 用法：/dshplace <pos> <item>
        //   · 先把物品**换到手上** ✓（模组自己找 0..35 ✓ 不需要有空快捷栏槽 ✓）
        //   · 目标格必须是**空气** ✓ 六邻格里要有**支撑面** ✓
        //   · 放完 **读世界真值复核** ✗ 并报出**实际放下的方块名** ✓（不听 useItemOn 的自述 ✗）
        d.register(Commands.literal("dshplace").requires(s -> s.hasPermission(PERM))
                .then(Commands.argument("pos", BlockPosArgument.blockPos())
                        .then(Commands.argument("item", StringArgumentType.string())
                                .executes(ctx -> place(ctx)))));

        // ── /dshdig —— ★显式挖掉一格（模组侧 ✓ 2026-10-01 补）★──────────────
        // 用法：/dshdig <pos>
        //   WHY ✗：★模组里以前**没有** `/dshdig`✗★ ⇒ 中间层走的是**模组之外**的老 Lua 桥 `dig_at`
        //     ⇒ 2026-10-01 安静通道实测（★只发它一条 ✗ 之后每 15 秒只扫一格 ✓）：
        //       ★**5 分钟（314 秒）那一格还是 cobblestone**✗★ —— 而同一个循环里
        //       ★`/dshplace`（在模组里 ✓）**每次都真改了世界**✗★（第③档就是被它卡住的 ✓）
        //   ★口径✗★：① 在 REACH 内 ✓ ② 目标格必须**不是空气** ✓
        //     ③ 走服务端 `gameMode.destroyBlock`（★假人自己的破坏逻辑 ⇒ 掉落物按原样 ✗
        //        掉出来的东西仍要自己捡 ✓ 与真人一致 ✓★）
        //     ④ ★挖完读**世界真值**复核✗★（★不听自述 ✗ P140/P164 同族 ✓★）
        d.register(Commands.literal("dshdo").requires(s -> s.hasPermission(PERM))
                .then(Commands.literal("status").executes(ctx -> doStatus(ctx)))
                .then(Commands.literal("stop").executes(ctx -> doStop(ctx)))
                .then(Commands.argument("plan", StringArgumentType.string())
                        .executes(ctx -> doStart(ctx))));

        d.register(Commands.literal("dshgoto").requires(s -> s.hasPermission(PERM))
                .then(Commands.argument("route", StringArgumentType.string())
                        .executes(ctx -> gotoStart(ctx))));

        d.register(Commands.literal("dshdig").requires(s -> s.hasPermission(PERM))
                .then(Commands.argument("pos", BlockPosArgument.blockPos())
                        .executes(ctx -> digBlock(ctx))));

        d.register(Commands.literal("dshstats").requires(s -> s.hasPermission(PERM))
                .executes(ctx -> stats(ctx)));

        // ── /dshuse —— ★对着方块的**指定面**右键★（补"没有客户端"最核心的缺口 ✓）──
        // 用法：/dshuse <pos> <face> [aimy] [--offhand]
        //   face  : up / down / north / south / east / west
        //   aimy  : 瞄准点在方块内的"高度比例" 0..1（默认 0.5 ✓）
        //           ★ 筛子必须给 0.15 左右：要从上方**射进碗里**（命中面 = up）★
        //           打侧面时筛子**完全不动、而且一声不响** ✗（错题本 P16 ✓）
        d.register(Commands.literal("dshuse").requires(s -> s.hasPermission(PERM))
                .then(Commands.argument("pos", BlockPosArgument.blockPos())
                        .then(Commands.argument("face", StringArgumentType.word())
                                .executes(ctx -> useOn(ctx, 0.5f))
                                .then(Commands.argument("aimy", FloatArgumentType.floatArg(0.0f, 1.0f))
                                        .executes(ctx -> useOn(ctx, FloatArgumentType.getFloat(ctx, "aimy")))))));

        // ── /dshcraft —— ★工作台合成（不开界面 ✓ 按服务端配方真扣真出）★ ────────
        d.register(Commands.literal("dshcraft").requires(s -> s.hasPermission(PERM))
                .then(Commands.literal("do")
                        .then(Commands.argument("item", StringArgumentType.string())
                                .executes(ctx -> craft(ctx, 1))
                                .then(Commands.argument("times", IntegerArgumentType.integer(1, MAX_TIMES))
                                        .executes(ctx -> craft(ctx, IntegerArgumentType.getInteger(ctx, "times"))))))
                .then(Commands.literal("can")
                        .then(Commands.argument("item", StringArgumentType.string())
                                .executes(ctx -> craftCan(ctx, 1))
                                .then(Commands.argument("times", IntegerArgumentType.integer(1, MAX_TIMES))
                                        .executes(ctx -> craftCan(ctx, IntegerArgumentType.getInteger(ctx, "times"))))))
                .then(Commands.literal("recipes")
                        .then(Commands.argument("item", StringArgumentType.string())
                                .executes(ctx -> craftRecipes(ctx)))));

        // ── /dshinv —— ★整理背包★（真人拖背包 ✗ 假人做不到 ✓ 这里补上）─────────
        // ── ★★§79.444✗★★：★`/dshtake` —— ★从容器取物品（★成品标准 1 的最后一块✗★）✗★
        d.register(Commands.literal("dshtake").requires(s -> s.hasPermission(PERM))
                .then(Commands.argument("pos", BlockPosArgument.blockPos())
                        .then(Commands.argument("item", StringArgumentType.string())
                                .executes(ctx -> invTake(ctx, Integer.MAX_VALUE))
                                .then(Commands.argument("count", IntegerArgumentType.integer(1))
                                        .executes(ctx -> invTake(ctx,
                                                IntegerArgumentType.getInteger(ctx, "count")))))));
        // ── ★★§79.445✗★★：★`/dshstore` —— ★把东西放进容器（★取出来的东西能放回去 ✗ 净零✗★）✗★
        d.register(Commands.literal("dshstore").requires(s -> s.hasPermission(PERM))
                .then(Commands.argument("pos", BlockPosArgument.blockPos())
                        .then(Commands.argument("item", StringArgumentType.string())
                                .executes(ctx -> invStore(ctx, Integer.MAX_VALUE))
                                .then(Commands.argument("count", IntegerArgumentType.integer(1))
                                        .executes(ctx -> invStore(ctx,
                                                IntegerArgumentType.getInteger(ctx, "count")))))));
        d.register(Commands.literal("dshinv").requires(s -> s.hasPermission(PERM))
                .then(Commands.literal("list").executes(ctx -> invList(ctx)))
                .then(Commands.literal("move")
                        .then(Commands.argument("from", IntegerArgumentType.integer(0, 40))
                                .then(Commands.argument("to", IntegerArgumentType.integer(0, 40))
                                        .executes(ctx -> invMove(ctx, Integer.MAX_VALUE))
                                        .then(Commands.argument("count", IntegerArgumentType.integer(1))
                                                .executes(ctx -> invMove(ctx, IntegerArgumentType.getInteger(ctx, "count")))))))
                .then(Commands.literal("drop")
                        .then(Commands.argument("slot", IntegerArgumentType.integer(0, 40))
                                .executes(ctx -> invDrop(ctx, Integer.MAX_VALUE))
                                .then(Commands.argument("count", IntegerArgumentType.integer(1))
                                        .executes(ctx -> invDrop(ctx, IntegerArgumentType.getInteger(ctx, "count"))))))
                .then(Commands.literal("hotbar")
                        .then(Commands.argument("slot", IntegerArgumentType.integer(0, 40))
                                .executes(ctx -> invHotbar(ctx))))
                .then(Commands.literal("equip")
                        .then(Commands.argument("slot", IntegerArgumentType.integer(0, 40))
                                .executes(ctx -> invEquip(ctx)))));

        // ── /dshent —— ★右键实体★（喂食 ✓ 繁殖 ✓ 挤奶 ✓ 剪毛 ✓）──────────────
        d.register(Commands.literal("dshent").requires(s -> s.hasPermission(PERM))
                .then(Commands.literal("use")
                        .then(Commands.argument("target", EntityArgument.entity())
                                .executes(ctx -> entUse(ctx))))
                .then(Commands.literal("info")
                        .then(Commands.argument("target", EntityArgument.entity())
                                .executes(ctx -> entInfo(ctx)))));

        // ══════════════════════════════════════════════════════════════════════
        // ── ★★v2.6：把"看"和"走"搬进模组★★（2026-09-19 晚 ✓）─────────────────
        //
        // 为什么这一版最值钱 ✗（**有实测数字** ✓ 见 docs/模组-容器存取与假人手.md §10 ✓）：
        //   · 读世界原先走 CC 的 `commands.getBlockInfos` ✗ 而它**一次只能 4³ 格** ✗
        //     ⇒ 2268 格要 42 次调用 = **3.5 s** ✗；寻路扫 7696 格 = **8 s 预算直接超时** ✗
        //   · 走路原先是 `player Bot move forward` **脉冲** ＋ 轮询位置 ✗
        //     ⇒ 空旷 1.2 s/途经点 ✓ 杂物区 **4.5 s/途经点 ＋ 重规划用尽后放弃** ✗
        //   ⇒ 同一件事在**服务端原生**做是微秒级 ✓
        //   ⇒ 所以这不是"快一点"✗ 而是 **消掉一整类失败** ✓（扫描超时 ✗ 卡住说不清原因 ✗）
        //
        // 另加两条"像真人"的：**吃东西走真人那条路** ✓（`ItemStack.use` ⇒ 有 1.6 秒咀嚼 ✓）
        // 和**空闲四处看** ✓（默认关 ✗ 原因见 `AUTO_IDLE` 的注释 ✓）
        // ══════════════════════════════════════════════════════════════════════

        // ── /dshver —— 报"**真正加载的是哪一版**"★ ──────────────────────────────
        //   ★为什么必须有它★ ✗：模组改动**必须关游戏进程重启** ✗（只退世界不加载 ✗）
        //   以前判"到底装上没有"只能去读 `logs/debug.log` ✗ 或看某个新字段 ✗
        //   ⇒ 现在一条指令就问出来 ✓（读的是**真实加载的 mod 版本** ✓ 不是常量 ✗）
        d.register(Commands.literal("dshver").requires(s -> s.hasPermission(PERM))
                .executes(ctx -> ver(ctx)));

        // ── /dshkbexport —— ★只读注册表导出★（§79.478）────────────────────────────
        //   ★做什么✗★：★把 `BuiltInRegistries.BLOCK` 里**所有方块 id**按字典序分页列出来 ✓
        //   ★不做什么✗★：★**不改任何判定逻辑** ✗ 一条都不改 ⇒ 只是"问世界本来有哪些方块" ✓
        //   ★为什么需要✗★：★覆盖率原先的分母是"三份离线代理的并集"（25719）✗ 不是真注册表
        //     ⇒ 有了这条就能算**精确覆盖率** ✓（欠账 ㊲ 的第 ① 项 ✓）
        //   用法：/dshkbexport [page]
        d.register(Commands.literal("dshkbexport").requires(s -> s.hasPermission(PERM))
                .executes(ctx -> kbexport(ctx, 1))
                .then(Commands.argument("page", IntegerArgumentType.integer(1))
                        .executes(ctx -> kbexport(ctx, IntegerArgumentType.getInteger(ctx, "page")))));

        // ── /dshstate —— ★只读：一个方块的**全部状态属性**（§79.487）────────────────
        //   ★为什么必须有✗★：★机器朝向（★facing／axis／自定义属性✗★）**只在运行时** ✗
        //   而且各模组属性名不同 ⇒ ★只能"全部倒出来" ✗ 不能按名字猜✗★ ✓
        //   ★也不改世界 ✗ 只读一格✗★
        d.register(Commands.literal("dshstate").requires(s -> s.hasPermission(PERM))
                .then(Commands.argument("pos", BlockPosArgument.blockPos())
                        .executes(ctx -> stateOf(ctx, BlockPosArgument.getLoadedBlockPos(ctx, "pos")))));

        // ── /dshcaps —— ★只读：逐面探测能力接口（§79.487）────────────────────────
        //   ★为什么必须有✗★：★"★这一面能不能进电／能不能出物品★"**就是接口的定义** ✗
        //   而 Forge 的 capability 正好是"★位置＋朝向★"查的 ✓
        //   ★FE 用 `canReceive/canExtract` 直接判 输入/输出/双向/没有 ✗ 不用名字表✓★
        d.register(Commands.literal("dshcaps").requires(s -> s.hasPermission(PERM))
                .then(Commands.argument("pos", BlockPosArgument.blockPos())
                        .executes(ctx -> capsOf(ctx, BlockPosArgument.getLoadedBlockPos(ctx, "pos")))));

        // ── /dshscan —— ★原生区域扫描★（取代 Lua 的 4³ 分块 ✗）──────────────────
        // 用法：/dshscan <from> <to> [match] [max] [page]
        //   match：按方块名**子串**筛 ✓ 给了它才逐格列 cells ✓（不给=只要聚合统计 ✓ 省流量 ✓）
        d.register(Commands.literal("dshscan").requires(s -> s.hasPermission(PERM))
                .then(Commands.argument("from", BlockPosArgument.blockPos())
                        .then(Commands.argument("to", BlockPosArgument.blockPos())
                                .executes(ctx -> scan(ctx, "", 64, 1))
                                .then(Commands.argument("match", StringArgumentType.string())
                                        .executes(ctx -> scan(ctx, StringArgumentType.getString(ctx, "match"), 64, 1))
                                        .then(Commands.argument("max", IntegerArgumentType.integer(1, 2000))
                                                .executes(ctx -> scan(ctx, StringArgumentType.getString(ctx, "match"),
                                                        IntegerArgumentType.getInteger(ctx, "max"), 1))
                                                .then(Commands.argument("page", IntegerArgumentType.integer(1))
                                                        .executes(ctx -> scan(ctx, StringArgumentType.getString(ctx, "match"),
                                                                IntegerArgumentType.getInteger(ctx, "max"),
                                                                IntegerArgumentType.getInteger(ctx, "page")))))))));

        // ── /dshmap ＋ /dshpath —— ★v2.15：地图与"只看不走的规划"★ ─────────────
        //   dshmap：一条指令画一整片（地表 ＋ 图例 ✓ 全 ASCII ✓）—— 中间层建图快 50 倍 ✓
        //   dshpath：只跑 A* 并摊开结果 ✓（诊断"到底能不能到"✓ 与中间层规划对比 ✓）
        d.register(Commands.literal("dshmap").requires(s -> s.hasPermission(PERM))
                .executes(ctx -> mapCmd(ctx, 10))
                .then(Commands.argument("radius", IntegerArgumentType.integer(1, 32))
                        .executes(ctx -> mapCmd(ctx, IntegerArgumentType.getInteger(ctx, "radius")))));
        d.register(Commands.literal("dshpath").requires(s -> s.hasPermission(PERM))
                .then(Commands.argument("pos", BlockPosArgument.blockPos())
                        .executes(ctx -> pathCmd(ctx))));

        // ── /dshdigest —— ★一条指令一份态势★（取代一次决策要 4~6 条 ✗）──────────
        //   含：位置/朝向/血/饿/经验/模式/手持 ＋ 背包(kinds,items,**free**) ＋ 附近实体
        //       ＋ **地上的掉落物**（带"**还剩多久消失**"★ 纪律⑤用得上 ✓）＋ 准星命中 ✓
        d.register(Commands.literal("dshdigest").requires(s -> s.hasPermission(PERM))
                .executes(ctx -> digest(ctx, 8.0, 360.0, 0))
                .then(Commands.argument("radius", FloatArgumentType.floatArg(1.0f, 64.0f))
                        .executes(ctx -> digest(ctx, FloatArgumentType.getFloat(ctx, "radius"), 360.0, 0))
                        // ★★v2.18.3 新增两个**可选**参数✗★★（2026-10-02 ✓ 抄"可见场景"的机制 ✓）
                        //   `fov`  ★视野锥角度✗★（默认 360 ＝ 旧行为 ✓ 前 60 度 ＝ 像玩家用眼睛 ✓）
                        //   `list` ★列出前 N 个实体/掉落物✗★（默认 0 ＝ 旧输出 ✓ 带 `类型@距离`✓）
                        .then(Commands.argument("fov", FloatArgumentType.floatArg(10.0f, 360.0f))
                                .executes(ctx -> digest(ctx, FloatArgumentType.getFloat(ctx, "radius"),
                                        FloatArgumentType.getFloat(ctx, "fov"), 0))
                                .then(Commands.argument("list", IntegerArgumentType.integer(0, 24))
                                        .executes(ctx -> digest(ctx,
                                                FloatArgumentType.getFloat(ctx, "radius"),
                                                FloatArgumentType.getFloat(ctx, "fov"),
                                                IntegerArgumentType.getInteger(ctx, "list")))))));

        // ── /dshleash —— ★★紧围栏✗★★（欠账 ⑰ ✓ 2026-10-03 ✓ 每 tick 自查 ✓）
        //   ★用法✗★：`/dshleash <max_drift> <seconds>` ｜ `/dshleash status` ｜ `/dshleash off` ✓
        //   ★为什么✗★：★中间层一次采样 ≈1 秒 ✗ 这期间能走 5~7 格 ⇒ 只能事后拦✗★
        //     （★§79.27 实测：围栏 1.5 ⇒ 停在 3.03 ✗ 围栏 2.0 ⇒ 停在 6.90 ✓★）
        //   ★拦的方式✗★：★**就地清输入**（`xxa/zza=0` ✗ 且**继续清**直到到期✓★）
        //     ＋ ★发 **ASCII 事件** `leash_stop why=fence moved=… max=… tick=…`✗★ ✓
        d.register(Commands.literal("dshleash").requires(s -> s.hasPermission(PERM))
                .then(Commands.literal("status").executes(ctx -> leashStatus(ctx)))
                .then(Commands.literal("off").executes(ctx -> leashOff(ctx)))
                .then(Commands.argument("max_drift", FloatArgumentType.floatArg(0.2f, 64.0f))
                        .then(Commands.argument("seconds", IntegerArgumentType.integer(1, 600))
                                .executes(ctx -> leashArm(ctx,
                                        FloatArgumentType.getFloat(ctx, "max_drift"),
                                        IntegerArgumentType.getInteger(ctx, "seconds"))))));

        // ── /dshthrow —— ★把手上的一件东西**真丢到地上**✗★（2026-10-02 ✓ 替掉 Carpet 的 `drop` ✓）
        //   ★为什么不用 Carpet 的 `drop`✗★（欠账 ⑪ ✓ 实测）：★`/player Bot drop` 之后
        //     背包 86⇒85 ✓ 而 **3 格内掉落实体 ＝ fail** ✗ 走回去也**没捡回来**✗★
        //     ⇒ ★它只让"东西离手" ✗ **不保证地上有一件能捡的**✗★
        //   ★本命令做什么✗★：★`held.shrink(1)` ＋ `p.drop(one, false, true)`✗★
        //     —— ★`Player#drop` 才是**真正生成掉落实体**的那条原版路✗★ ✓
        //   ★报文✗★：★只报**事实**（丢前/丢后 held 有几件 ✗ 丢出去的是哪个物品 ✓）★
        d.register(Commands.literal("dshthrow").requires(s -> s.hasPermission(PERM))
                .executes(ctx -> throwHeld(ctx, 1))
                .then(Commands.argument("times", IntegerArgumentType.integer(1, 4))
                        .executes(ctx -> throwHeld(ctx, IntegerArgumentType.getInteger(ctx, "times")))));

        // ── /dshlook —— 准星射线（方块/实体 ＋ **面** ＋ 距离 ＋ **可达性**）───────
        //   ★可达性判定是重点★ ✗：把 P16 那类"打得中但**一声不响、完全无效**"✗
        //   从"事后才发现"变成"**调用点就能问**"✓（真人够不着就是够不着 ✓）
        // ── /dshturn —— ★平滑转身（§79.495）★ ───────────────────────────────
        //   ★不是"一步到位"✗★：★按 tick 走**梯形角速度**（★加速-匀速-减速✗★）✗
        //   ★验收✗★：★`tools/turn_profile.py` 的 N3 四条（★起步不许全速 ✗ 中段匀速 ✗ 收尾减速 ✗ 过冲≤2✗★）✗★
        d.register(Commands.literal("dshturn").requires(s -> s.hasPermission(PERM))
                .then(Commands.argument("deg", FloatArgumentType.floatArg(-720f, 720f))
                        .executes(ctx -> turnStart(ctx,
                                FloatArgumentType.getFloat(ctx, "deg"), 0))
                        .then(Commands.argument("ticks", IntegerArgumentType.integer(2, 60))
                                .executes(ctx -> turnStart(ctx,
                                        FloatArgumentType.getFloat(ctx, "deg"),
                                        IntegerArgumentType.getInteger(ctx, "ticks"))))));

        // ── /dshyawtrace —— ★最近 n tick 的 yaw（★等效 20Hz✗★）────────────────
        d.register(Commands.literal("dshyawbracket").requires(s -> s.hasPermission(PERM))
                .executes(ctx -> {
                    StringBuilder sb = new StringBuilder();
                    for (int k = 0; k < BRACKET_LOG.length; k++) {
                        String s2 = BRACKET_LOG[k];
                        if (s2 != null) {
                            if (sb.length() > 0) {
                                sb.append(" | ");
                            }
                            sb.append(s2);
                        }
                    }
                    ok(ctx.getSource(), "dshyawbracket n=" + BRACKET_N + " last=[" + sb + "]");
                    return 1;
                }));

        d.register(Commands.literal("dshhold").requires(s -> s.hasPermission(PERM))
                .executes(ctx -> holdCmd(ctx, HOLD_ON))
                .then(Commands.literal("on").executes(ctx -> holdCmd(ctx, true)))
                .then(Commands.literal("off").executes(ctx -> holdCmd(ctx, false))));

        d.register(Commands.literal("dshyawtrace").requires(s -> s.hasPermission(PERM))
                .executes(ctx -> yawTrace(ctx, 40))
                .then(Commands.argument("n", IntegerArgumentType.integer(4, 64))
                        .executes(ctx -> yawTrace(ctx, IntegerArgumentType.getInteger(ctx, "n")))));

        // ── /dshyawprobe —— ★2.56.0（N3）一次性 yaw 写者探针★（只读；结果落 logs/yawprobe.log）──
        d.register(Commands.literal("dshyawprobe").requires(s -> s.hasPermission(PERM))
                .executes(ctx -> yawpReport(ctx))
                .then(Commands.literal("start")
                        .executes(ctx -> yawpStart(ctx, 200))
                        .then(Commands.argument("ticks", IntegerArgumentType.integer(20, 4000))
                                .executes(ctx -> yawpStart(ctx,
                                        IntegerArgumentType.getInteger(ctx, "ticks")))))
                .then(Commands.literal("stop").executes(ctx -> {
                    yawpStop();
                    ok(ctx.getSource(), "dshyawprobe state=stopped");
                    return 1;
                }))
                .then(Commands.literal("report").executes(ctx -> yawpReport(ctx)))
                .then(Commands.literal("bus").executes(ctx -> yawpBus(ctx))));

        // ── /dshhttp ＋ /dshreqs —— ★2.56.0：并发/令牌/白名单自报 ＋ 请求账本★（只读）──
        d.register(Commands.literal("dshhttp").requires(s -> s.hasPermission(PERM))
                .executes(ctx -> HttpBridge.httpDiag(ctx)));
        d.register(Commands.literal("dshreqs").requires(s -> s.hasPermission(PERM))
                .executes(ctx -> HttpBridge.httpReqs(ctx, 20))
                .then(Commands.argument("n", IntegerArgumentType.integer(1, 64))
                        .executes(ctx -> HttpBridge.httpReqs(ctx, IntegerArgumentType.getInteger(ctx, "n")))));

        d.register(Commands.literal("dshlook").requires(s -> s.hasPermission(PERM))
                .executes(ctx -> look(ctx, REACH))
                .then(Commands.argument("reach", FloatArgumentType.floatArg(1.0f, 64.0f))
                        .executes(ctx -> look(ctx, FloatArgumentType.getFloat(ctx, "reach")))));

        // ── /dshwalk —— ★原生连续行走★（像真人按住 W ✓ 服务器**逐 tick** 推进 ✓）──
        //   一条指令 = 一整段路 ✓（不再是"一格一条指令"✗，也不再靠 `tp` ✗）
        d.register(Commands.literal("dshwalk").requires(s -> s.hasPermission(PERM))
                .executes(ctx -> walkStatus(ctx))
                .then(Commands.literal("stop").executes(ctx -> walkStop(ctx)))
                .then(Commands.argument("pos", BlockPosArgument.blockPos())
                        .executes(ctx -> walkStart(ctx, 10000, false))
                        .then(Commands.argument("ms", IntegerArgumentType.integer(100, 120000))
                                .executes(ctx -> walkStart(ctx, IntegerArgumentType.getInteger(ctx, "ms"), false))
                                .then(Commands.literal("exact")
                                        .executes(ctx -> walkStart(ctx,
                                                IntegerArgumentType.getInteger(ctx, "ms"), true))))));

        // ── /dshevents —— ★增量事件流★（从"我来轮询"变"它告诉我"✓）────────────
        //   记：受伤 ✓ 吃东西 ✓ 背包增减 ✓ 模式变化（P17 的创造模式警报 ✓）
        //      **位置瞬移**（抓 `tp` ✓ 给"不走 tp"那条纪律当哨兵 ✓）
        //      **地上掉落物** ＋ **快消失的掉落物**（★P20 那次丢 25 个绿宝石的警报 ✓★）
        d.register(Commands.literal("dshevents").requires(s -> s.hasPermission(PERM))
                .executes(ctx -> events(ctx, -1))
                .then(Commands.argument("since", IntegerArgumentType.integer(0))
                        .executes(ctx -> events(ctx, IntegerArgumentType.getInteger(ctx, "since"))))
                .then(Commands.literal("watch")
                        .then(Commands.argument("name", StringArgumentType.word())
                                .executes(ctx -> eventsWatch(ctx)))));

        // ── /dshauto —— 自动行为（吃 ✓ 空闲看四周 ✓）──────────────────────────
        d.register(Commands.literal("dshauto").requires(s -> s.hasPermission(PERM))
                .executes(ctx -> autoStatus(ctx))
                .then(Commands.literal("eat")
                        .then(Commands.literal("on").executes(ctx -> autoEat(ctx, true, AUTO_EAT_MIN)))
                        .then(Commands.literal("off").executes(ctx -> autoEat(ctx, false, AUTO_EAT_MIN)))
                        .then(Commands.argument("minfood", IntegerArgumentType.integer(1, 19))
                                .executes(ctx -> autoEat(ctx, true, IntegerArgumentType.getInteger(ctx, "minfood")))))
                .then(Commands.literal("idle")
                        .then(Commands.literal("on").executes(ctx -> autoIdle(ctx, true)))
                        .then(Commands.literal("off").executes(ctx -> autoIdle(ctx, false)))));

        // ── /dshkb —— ★注册表**只读**导出★（2026-10-03 ✓ 用户拍板：命令名 `dshkb` ✓
        //    碰撞名集七类 ＋ `liquid` ✓ 落盘 `logs/blockkb.json` ✓ 见
        //    `docs/方案-注册表只读导出.md` ✓★）────────────────────────────────────
        //  ★它**只读注册表** ✗ 不读世界 ✗ 不改任何判定 ✗ 一次调用写**一个文件**✗★ ✓
        //  ★为什么必须写文件✗★：★回执有长度上限（★实测约 1600 字✗★）✗ 而注册表有两万多个
        //    方块 ✗ 走回执根本装不下 ✓ 逐格问一次世界是 608 ms ⇒ 4 小时 ✗★ ✓
        d.register(Commands.literal("dshkb").requires(s -> s.hasPermission(PERM))
                .executes(ctx -> kbExport(ctx, ""))
                .then(Commands.argument("ns", StringArgumentType.word())
                        .executes(ctx -> kbExport(ctx,
                                StringArgumentType.getString(ctx, "ns")))));
    }

    // ══════════════════════════════════════════════════════════════════════════
    // /dshkb —— ★注册表只读导出（★物理真值 ✗ 不含语义✗★）
    // ══════════════════════════════════════════════════════════════════════════

    /** ★碰撞族名（★几何 ✗ **不含**语义✓★）
     *
     *  ★取值与理由（★用户 2026-10-03 拍板✗★）✗★：
     *    `liquid`     水／岩浆 —— ★物理上是"游"不是"走" ✗ 所以**必须**与 `none` 分开✗★ ✓
     *    `none`       碰撞箱**空**（★空气 ✗ 花草 ✗ 火把 ✓★）
     *    `full`       顶面 ~1.0（★整方块✓★）
     *    `fence_15`   顶面 ≥ 1.4（★栅栏／墙 ✗ 1.5✓★）
     *    `slab`       顶面 0.45~0.55（★半砖 0.5✓★）
     *    `snow_layer` 顶面 < 0.45（★雪层 0.125 ✗ 地毯 0.0625 ✓★）
     *    `other`      ★以上都不是 ⇒ **必须**看 `max_height`✗★（★用户原话：★"★`other` 必须永远带
     *                 `max_height` ✗ 消费者就不许为 `other` 写特例★"✓★）
     *  ⚠ ★`canopy` **不在这里**✗★：★树叶的碰撞箱就是**整方块** ✗ 碰撞**看不出**它是树冠 ✗
     *    ⇒ ★它是**语义**（★标签 `leaves`✓★）✗ 由 Python 侧的标签层给 ✗ 不许混进物理导出✗★ ✓
     *  ⚠ ★阈值 0.5 与 `floorOk` **同源**✗★（★见那段的 v2.17 教训：★薄板不是一整格地板✓★）✗
     *    ★这里只是把"★≥0.5★"那条界**拆细**成 slab／snow_layer ✗ 不改它的方向✗★ ✓
     */
    private static String kbFamily(BlockState st, double h) {
        if (st.getBlock() instanceof LiquidBlock) {
            return "liquid";
        }
        if (st.getCollisionShape(EmptyBlockGetter.INSTANCE, BlockPos.ZERO).isEmpty()) {
            return "none";
        }
        if (h >= 1.4) {
            return "fence_15";
        }
        if (h >= 0.999) {
            return "full";
        }
        if (h >= 0.45) {
            return "slab";
        }
        if (h >= 0.02) {
            return "snow_layer";
        }
        return "other";
    }

    /** ★`/dshkb [ns]`✗★ —— ★一次调用写一个 JSON ✗ 只读注册表✗★ */
    private static int kbExport(CommandContext<CommandSourceStack> ctx, String ns) {
        CommandSourceStack src = ctx.getSource();
        long t0 = System.currentTimeMillis();
        java.io.File dir = new java.io.File("logs");
        java.io.File out = new java.io.File(dir, ns.isEmpty() ? "blockkb.json"
                : ("blockkb." + ns.replace(':', '_') + ".json"));
        int n = 0;
        int errs = 0;
        java.util.TreeMap<String, Integer> fam = new java.util.TreeMap<>();
        java.util.TreeMap<String, StringBuilder> rows = new java.util.TreeMap<>();
        for (ResourceLocation id : BuiltInRegistries.BLOCK.keySet()) {
            if (!ns.isEmpty() && !id.getNamespace().equals(ns)) {
                continue;
            }
            try {
                BlockState st = BuiltInRegistries.BLOCK.get(id).defaultBlockState();
                var shape = st.getCollisionShape(EmptyBlockGetter.INSTANCE, BlockPos.ZERO);
                double h = shape.isEmpty() ? 0.0 : shape.max(Direction.Axis.Y);
                String f = kbFamily(st, h);
                fam.merge(f, 1, Integer::sum);
                boolean be = st.hasBlockEntity();
                float dt = st.getDestroySpeed(EmptyBlockGetter.INSTANCE, BlockPos.ZERO);
                StringBuilder sb = new StringBuilder();
                sb.append("  \"").append(id).append("\": {\"family\": \"").append(f)
                  .append("\", \"max_height\": ").append(fmt4(h))
                  .append(", \"has_block_entity\": ").append(be)
                  .append(", \"destroy_time\": ").append(fmt4(dt))
                  .append(", \"empty\": ").append(shape.isEmpty()).append("}");
                rows.put(id.toString(), sb);
                n++;
            } catch (Throwable t) {
                // ★★失败要吵✗★★（★规格 §4.5：★不许静默跳过✗★）
                errs++;
                if (errs <= 5) {
                    src.sendSuccess(() -> Component.literal("!! " + id + " ⇒ " + t), false);
                }
            }
        }
        StringBuilder js = new StringBuilder();
        js.append("{\n \"schema\": \"dshbridge/registry_blocks@1\",\n");
        js.append(" \"exported_at\": \"").append(java.time.LocalDateTime.now()).append("\",\n");
        js.append(" \"mod_version\": \"").append(modVersion()).append("\",\n");
        js.append(" \"filter\": \"").append(ns.isEmpty() ? "all" : ns).append("\",\n");
        js.append(" \"count\": ").append(n).append(",\n");
        js.append(" \"errors\": ").append(errs).append(",\n");
        js.append(" \"families\": {");
        boolean first = true;
        for (var e : fam.entrySet()) {
            if (!first) {
                js.append(", ");
            }
            js.append("\"").append(e.getKey()).append("\": ").append(e.getValue());
            first = false;
        }
        js.append("},\n \"blocks\": {\n");
        first = true;
        for (var e : rows.entrySet()) {
            if (!first) {
                js.append(",\n");
            }
            js.append(e.getValue());
            first = false;
        }
        js.append("\n }\n}\n");
        try {
            if (!dir.isDirectory() && !dir.mkdirs()) {
                src.sendFailure(Component.literal("dshkb: 建不出 logs/ 目录"));
                return 0;
            }
            try (java.io.Writer w = new java.io.OutputStreamWriter(
                    new java.io.FileOutputStream(out), java.nio.charset.StandardCharsets.UTF_8)) {
                w.write(js.toString());
            }
        } catch (Throwable t) {
            src.sendFailure(Component.literal("dshkb: 写不出 " + out + " ⇒ " + t));
            return 0;
        }
        long ms = System.currentTimeMillis() - t0;
        StringBuilder r = new StringBuilder();
        r.append("dshkb count=").append(n).append(" errors=").append(errs);
        for (var e : fam.entrySet()) {
            r.append(" ").append(e.getKey()).append("=").append(e.getValue());
        }
        r.append(" path=").append(out.getPath()).append(" ms=").append(ms);
        final String line = r.toString();
        src.sendSuccess(() -> Component.literal(line), false);
        return n;
    }

    /** ★四位小数 ✗ 定长 ✗ 免得不同 JVM／地区设置印出不同写法✗★ */
    private static String fmt4(double v) {
        return String.format(java.util.Locale.ROOT, "%.4f", v);
    }

    /** ★真正加载的模组版本✗★（★`/dshver` 与 `/dshkb` 都问它 ✗ 一份实现✓★） */
    private static String modVersion() {
        return ModList.get().getModContainerById("dshbridge")
                .map(c -> c.getModInfo().getVersion().toString()).orElse("unknown");
    }

    // ══════════════════════════════════════════════════════════════════════════
    // 工具
    // ══════════════════════════════════════════════════════════════════════════

    // ══ ★★v2.12.0：皮肤系统★★（★通用性契约见 docs/模组-皮肤系统.md ✓★）══
    // 实测前提 ✗：资源包覆盖默认皮肤贴图**对假人无效** ✓（2026-09-21 三个包全合法 ✓
    //   已选中 ✓ 已加载 ✓ 外观不变 ✗）⇒ 只能走服务端：把皮肤写进玩家档案的 textures 属性 ✓
    //   而客户端**只认 URL** ✗ ⇒ 模组自己起一个**只绑回环**的小 HTTP 服务 ✓
    // 通用性六条 ✓（G1 加皮肤不用重编译 ✓｜G2 代码里不写死名字/数量 ✓｜G3 任何玩家 ✓｜
    //   G4 任何世界（回环＋自动端口＋可换 base）✓｜G5 不依赖外部服务 ✓｜G6 坏图要吵 ✗）
    private static final java.util.Map<String, Object[]> SKINS = new java.util.LinkedHashMap<>();
    private static com.sun.net.httpserver.HttpServer SKIN_HTTP = null;
    private static int SKIN_PORT = 0;
    private static volatile String SKIN_BASE = null;
    /** ★v2.12.2：每次推都换一个序号★ ✗（用户观察 C ✓：`?v=` 只用内容指纹时 ✓
     *  内容不变 ⇒ URL 不变 ⇒ 客户端**一直吃缓存** ⇒ 表现成"完全没反应"✗）
     *  ⇒ 把序号混进指纹 ✓ 强制重下 ✓ */
    private static final java.util.concurrent.atomic.AtomicInteger SKIN_SEQ =
            new java.util.concurrent.atomic.AtomicInteger(0);

    private static byte[] readBytes(java.io.InputStream in) throws java.io.IOException {
        java.io.ByteArrayOutputStream bo = new java.io.ByteArrayOutputStream();
        byte[] buf = new byte[8192];
        int n;
        while ((n = in.read(buf)) > 0) {
            bo.write(buf, 0, n);
        }
        return bo.toByteArray();
    }

    private static String sha1hex(byte[] b) {
        try {
            java.security.MessageDigest md = java.security.MessageDigest.getInstance("SHA-1");
            byte[] d = md.digest(b);
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < 8; i++) {
                sb.append(String.format("%02x", d[i]));
            }
            return sb.toString();
        } catch (Exception e) {
            System.out.println("[dshbridge] sha1hex FAILED -> " + e);
            return "0";
        }
    }

    /** PNG 头校验 ✓：必须 64x64 且 RGBA（color type 6 ✓）—— G6：不合格就**明确拒绝**✗ */
    private static String pngProblem(byte[] p) {
        if (p == null || p.length < 26 || p[0] != (byte) 0x89 || p[1] != 'P') {
            return "not a PNG";
        }
        int w = ((p[16] & 0xFF) << 24) | ((p[17] & 0xFF) << 16) | ((p[18] & 0xFF) << 8) | (p[19] & 0xFF);
        int h = ((p[20] & 0xFF) << 24) | ((p[21] & 0xFF) << 16) | ((p[22] & 0xFF) << 8) | (p[23] & 0xFF);
        int ct = p[25] & 0xFF;
        if (w != 64 || h != 64) {
            return "size " + w + "x" + h + " (need 64x64)";
        }
        if (ct != 6) {
            return "color type " + ct + " (need 6 = RGBA)";
        }
        return null;
    }

    /** 极简 JSON 取值 ✓（不引第三方库 ✗；skin 清单是我们自己的格式 ✓） */
    private static java.util.List<String[]> parseSkinList(String json) {
        java.util.List<String[]> r = new java.util.ArrayList<>();
        int i = json.indexOf("\"skins\"");
        if (i < 0) {
            return r;
        }
        int arr = json.indexOf('[', i), end = json.lastIndexOf(']');
        if (arr < 0 || end < arr) {
            return r;
        }
        for (String part : json.substring(arr + 1, end).split("\\}")) {
            String file = field(part, "file"), name = field(part, "name"),
                    model = field(part, "model"), note = field(part, "note");
            if (file != null) {
                r.add(new String[]{file, name, model, note});
            }
        }
        return r;
    }

    private static String field(String s, String key) {
        int i = s.indexOf("\"" + key + "\"");
        if (i < 0) {
            return null;
        }
        int c = s.indexOf(':', i), q1 = s.indexOf('"', c + 1), q2 = s.indexOf('"', q1 + 1);
        return (q1 < 0 || q2 < 0) ? null : s.substring(q1 + 1, q2);
    }

    private static void putSkin(String name, byte[] png, String model, String from) {
        String bad = pngProblem(png);
        if (bad != null) {
            // G6 ✓：坏图**记下来但不启用** ✗（列表里要能看到它为什么不合格 ✓）
            SKINS.put(name, new Object[]{null, from, model == null ? "wide" : model, sha1hex(png), bad});
            return;
        }
        SKINS.put(name, new Object[]{png, from, model == null ? "wide" : model, sha1hex(png), null});
    }

    /** 扫两个目录 ✓（外部优先 ✓ 名字全部来自数据 ✓ 代码里一个皮肤名都不写 ✗ = G2 ✓） */
    private static synchronized void loadSkins() {
        SKINS.clear();
        for (String root : new String[]{"assets/dshbridge/skins", "config/dshbridge/skins"}) {
            try {
                String json = null;
                java.io.InputStream jin = DshBridgeMod.class.getClassLoader().getResourceAsStream(root + "/skins.json");
                if (jin != null) {
                    json = new String(readBytes(jin), java.nio.charset.StandardCharsets.UTF_8);
                    jin.close();
                }
                if (json != null) {
                    for (String[] e : parseSkinList(json)) {
                        java.io.InputStream in = DshBridgeMod.class.getClassLoader()
                                .getResourceAsStream(root + "/" + e[0]);
                        if (in == null) {
                            continue;
                        }
                        byte[] png = readBytes(in);
                        in.close();
                        String nm = (e[1] == null || e[1].isEmpty())
                                ? e[0].replaceAll("\\.png$", "") : e[1];
                        putSkin(nm, png, e[2], root);
                    }
                }
            } catch (Exception ignored) {
                // 一个来源坏了不影响另一个 ✓（但要能看出来：列表里就没有它的条目 ✓）
            }
        }
        // ★G1：外部目录里没写进 json 的 PNG 也**直接发现** ✓（丢图即用 ✓ 不用重编译 ✗）
        try {
            java.nio.file.Path ext = java.nio.file.Paths.get("config", "dshbridge", "skins");
            if (java.nio.file.Files.isDirectory(ext)) {
                try (java.util.stream.Stream<java.nio.file.Path> st = java.nio.file.Files.list(ext)) {
                    for (java.nio.file.Path p : st.toList()) {
                        String fn = p.getFileName().toString();
                        if (!fn.toLowerCase().endsWith(".png")) {
                            continue;
                        }
                        String nm = fn.substring(0, fn.length() - 4);
                        if (SKINS.containsKey(nm)) {
                            continue;                       // json 里已声明 ✓（外部赢 ✓）
                        }
                        putSkin(nm, java.nio.file.Files.readAllBytes(p), "wide", "config");
                    }
                }
            }
        } catch (Exception ignored) {
            // 外部皮肤目录扫不动 ⇒ 那批皮肤静默消失 ⇒ 说一声
            System.out.println("[dshbridge] external skin dir FAILED -> " + ignored);
        }
    }

    /** ★皮肤 HTTP 的访问日志★ ✗（写到游戏目录下的 logs/skin_http.log ✓ 你也能直接看 ✓） */
    private static synchronized void skinLog(String line) {
        try {
            java.nio.file.Path p = java.nio.file.Paths.get("logs", "skin_http.log");
            java.nio.file.Files.createDirectories(p.getParent());
            java.nio.file.Files.writeString(p,
                    "[" + java.time.LocalTime.now().withNano(0) + "] " + line + "\n",
                    java.nio.charset.StandardCharsets.UTF_8,
                    java.nio.file.StandardOpenOption.CREATE, java.nio.file.StandardOpenOption.APPEND);
        } catch (Exception ignored) {
        }
    }

    /** ★给别的类用的入口：确保皮肤服务在跑，并返回它的 base★ ✗（v2.14.0 ✓）
     *  为什么需要它 ✗：实测发现**登录那一刻**注入才被客户端采纳 ✓
     *  而 `BotSkin` 正在那个时机 ✓ ⇒ 让它"没配 URL 时"用**模组自带**的服务 ✓
     *  ⇒ 零配置 ✓ 零外部依赖 ✓（不再需要 tools/skin_server.py ✗） */
    public static String ensureSkinBase() {
        try {
            if (SKIN_HTTP == null) {
                startSkinHttp();
            }
            return SKIN_BASE;
        } catch (Exception e) {
            return null;
        }
    }

    /** ★按状态文件给某个玩家换上他"记过"的那个皮肤★ ✗（没记过就用默认 deepseek ✓） */
    public static boolean applyChosenSkin(ServerPlayer p) {
        try {
            skinStateLoad();
            if (SKINS.isEmpty()) {
                loadSkins();
            }
            if (ensureSkinBase() == null) {
                return false;
            }
            String name = SKIN_CHOSEN.getOrDefault(p.getName().getString(), "deepseek");
            if (!SKINS.containsKey(name) && !SKINS.isEmpty()) {
                name = SKINS.keySet().iterator().next();
            }
            boolean okk = applySkin(p, name);
            if (okk) {
                ev("skin_boot", "player=" + p.getName().getString() + " skin=" + name
                        + " via=botskin-login");
            }
            return okk;
        } catch (Exception e) {
            return false;
        }
    }

    private static void startSkinHttp() {

        if (SKIN_HTTP != null) {
            return;
        }
        synchronized (SKINS) {
            if (SKIN_HTTP != null) {
                return;
            }
            try {
                // ★★实测修 ✗（2026-09-21 v2.12.0 验收 A7 抓到 ✓）★★：
                //   原来用 `InetAddress.getLoopbackAddress()` ✗ —— 它会返回 **IPv6 的 `::1`** ✓
                //   而我们的 URL 写的是 **IPv4 字面量** `http://127.0.0.1:<port>` ✗
                //   ⇒ 实测：`count=3 port=59127` 却 **`127.0.0.1` 连不上** ✓ ⇒ 客户端下载皮肤必失败 ✗
                //   ⇒ 改成**显式绑 IPv4 回环** ✓（与 URL 一致 ✓）
                com.sun.net.httpserver.HttpServer srv = com.sun.net.httpserver.HttpServer.create(
                        new java.net.InetSocketAddress("127.0.0.1", 0), 0);
                srv.createContext("/skin/", ex -> {
                    // ★v2.13.2：访问日志 ✗ —— 客户端到底来没来下载，全靠它 ✓
                    //   三种可能必须分开 ✓：没来 ✗ / 来了但失败 ✓ / 来了且成功 ✓（对应三种修法 ✗）
                    long tReq = System.nanoTime();
                    String reqPath = ex.getRequestURI().toString();
                    String from = String.valueOf(ex.getRemoteAddress());
                    try {
                        String path = ex.getRequestURI().getPath();       // /skin/<name>.png ✓
                        String nm = path.substring(path.lastIndexOf('/') + 1).replaceAll("\\.png$", "");
                        Object[] e = SKINS.get(nm);
                        byte[] body = (e == null) ? null : (byte[]) e[0];
                        skinLog("REQ from=" + from + " path=" + reqPath
                                + " found=" + (body != null)
                                + " bytes=" + (body == null ? 0 : body.length)
                                + " us=" + ((System.nanoTime() - tReq) / 1000L));
                        if (body == null) {
                            ex.sendResponseHeaders(404, -1);
                        } else {
                            ex.getResponseHeaders().add("Content-Type", "image/png");
                            ex.sendResponseHeaders(200, body.length);
                            try (java.io.OutputStream os = ex.getResponseBody()) {
                                os.write(body);
                            }
                        }
                    } catch (Exception ignored) {
                    } finally {
                        ex.close();
                    }
                });
                srv.setExecutor(null);
                srv.start();
                SKIN_HTTP = srv;
                SKIN_PORT = srv.getAddress().getPort();
                SKIN_BASE = "http://127.0.0.1:" + SKIN_PORT;              // ★只绑回环★ ✓ G4 ✓
            } catch (Exception e) {
                SKIN_HTTP = null;
            }
        }
    }

    /** ★让客户端立刻重新读一遍这条玩家信息★ ✗
     *  ⚠ 踩坑记录 ✓（2026-09-21）：我第一版用的是
     *    `ClientboundPlayerInfoUpdatePacket.Action.UPDATE_GAME_PROFILE` ✗
     *    —— 那是 **1.20.2 才加的** ✗ 而我们是 **1.20.1** ✓ ⇒ 编译期"找不到符号" ✓（一次两处 ✓）
     *  ⇒ 改用 1.20.1 就有的常规做法 ✓：**移除 ＋ 重新登记** ✓（客户端会重读档案 ⇒ 皮肤刷新 ✓）
     */
    private static void refreshSkinOnClient(ServerPlayer p) {
        try {
            if (p.connection == null) {
                return;
            }
            p.connection.send(new net.minecraft.network.protocol.game.ClientboundPlayerInfoRemovePacket(
                    java.util.List.of(p.getUUID())));
            p.connection.send(net.minecraft.network.protocol.game.ClientboundPlayerInfoUpdatePacket
                    .createPlayerInitializing(java.util.List.of(p)));
            // ★v2.12.3：**把实体也重建一遍** ✗（用户观察："完全没反应" ✓）
            //   只更新 PlayerInfo 是**不够的** ✓：实体早就在世界里时 ✓
            //   客户端仍旧用它自己那份老数据画 ⇒ 外观不变 ✗
            //   顺序要点 ✓：先 PlayerInfo（含皮肤 ✓）再加实体 ✓ 反过来客户端就没皮肤 ✓
            p.connection.send(new net.minecraft.network.protocol.game.ClientboundRemoveEntitiesPacket(
                    p.getId()));
            p.connection.send(new net.minecraft.network.protocol.game.ClientboundAddPlayerPacket(p));
        } catch (Exception ignored) {
            // 推不动就算了 ✓ —— 但**下一次重连一定会生效** ✓（皮肤已经写进档案了 ✓）
        }
    }

    // ══ ★★v2.13.1：皮肤持久化 ＋ 自愈★★ ✗（用户实测："皮肤又掉了" ✓）══
    //   缺的是"记住"✗：`/dskskin` 只是当次注入 ✓ ⇒ 世界重启/假人重生 ⇒ 档案全新 ⇒ 掉 ✓
    private static final java.nio.file.Path SKIN_STATE =
            java.nio.file.Paths.get("config", "dshbridge", "skins_state.json");
    private static final java.util.Map<String, String> SKIN_CHOSEN = new java.util.concurrent.ConcurrentHashMap<>();
    private static long wSkinCheck = -1;

    private static void skinStateLoad() {
        try {
            if (!java.nio.file.Files.isRegularFile(SKIN_STATE)) {
                return;
            }
            String txt = java.nio.file.Files.readString(SKIN_STATE, java.nio.charset.StandardCharsets.UTF_8);
            java.util.regex.Matcher m = java.util.regex.Pattern
                    .compile("\"([^\"]+)\"\\s*:\\s*\"([^\"]+)\"").matcher(txt);
            while (m.find()) {
                SKIN_CHOSEN.put(m.group(1), m.group(2));
            }
        } catch (Exception ignored) {
            // 读坏了不许装作"没人选过皮肤" ⇒ 说一声（下一次 save 会覆盖它 ✗）
            System.out.println("[dshbridge] skinStateLoad FAILED -> " + ignored);
        }
    }

    private static void skinStateSave() {
        try {
            java.nio.file.Files.createDirectories(SKIN_STATE.getParent());
            StringBuilder sb = new StringBuilder("{\n");
            boolean first = true;
            for (java.util.Map.Entry<String, String> e : SKIN_CHOSEN.entrySet()) {
                sb.append(first ? "" : ",\n").append("  \"").append(e.getKey())
                        .append("\": \"").append(e.getValue()).append("\"");
                first = false;
            }
            sb.append("\n}\n");
            java.nio.file.Files.writeString(SKIN_STATE, sb.toString(),
                    java.nio.charset.StandardCharsets.UTF_8);
        } catch (Exception ignored) {
            // 写不进去 ⇒ 皮肤选择会在重启后静默丢失 ⇒ 说一声
            System.out.println("[dshbridge] skinStateSave FAILED -> " + ignored);
        }
    }

    // ══ ★★v2.18：只对"我们的那个身体"生效的**死亡保险**★★ ✗
    //
    // 用户原话 ✓：「把一整包家当弄丢的身体，给 bot 上一个死亡不掉落就行了吧」✓ —— ★方向是对的✗✓★
    //
    // ★但"掉虚空"恰好是现有机制兜不住的那一种✗★（实测 ✓ 见错题本归档 §25.2 ✓）：
    //   实例里装着 **Corail Tombstone** ✓ 配置已经是 `chance_loss_on_death = 0` ✓
    //   ⇒ 死亡时**一个都不掉**、全进墓碑 ✓ —— 可★**墓碑生成在死亡点**✗★
    //   ⇒ 掉进虚空 ⇒ **墓碑也在虚空里** ⇒ 实测 `tombstone/grave/corpse/death` **全 0 命中** ✗ 取不回 ✗
    //
    // ★所以这里**不碰全局 gamerule**✗★（那会改**玩家自己的**游戏 ✓ 用户明确"先挂起"✗）——
    //   只在**这一层**给这一个身体保住背包 ✓：
    //     ① 死时把背包**搬走**（内存 ＋ 落盘 NBT ✓）⇒ 再**清空它** ✓
    //        ★这一步是关键✗★：不搬走的话 ⇒ 墓碑存一份 ＋ 我们又还一份 ⇒ **凭空多一份**✗（复制 bug ✓）
    //     ② 它回来时（`/player Bot spawn` ✓）⇒ 背包**还回去** ✓ 并**送回上一次的安全落脚点** ✓
    //
    // ★同时留账✗★：`bot_died` / `bot_revived` 两条 **ASCII 事件** ✓ ⇒
    //   ★"掉虚空"仍然是**失败**✗★ —— 保险只保证**不毁家当** ✓
    //   ★不许拿它冒充"没掉下去"✗★（那是 D3 的正面判据 ✓ 见 docs/接口契约-伙伴v1.0.md 第 9 节 ✓）
    //
    // ⚠ 账要记 ✓：`docs/自给清单.md` 必须记一笔 ✗ —— 它改变的是"死亡意味着什么" ✓
    //   （同族：P17 创造模式"死亡不掉落"让自给证据失真 ✓）
    private static final java.nio.file.Path DEATH_STASH =
            java.nio.file.Paths.get("config", "dshbridge", "bot_death_stash.nbt");

    /** 死时扣下的那一包（**只保一个身体** ⇒ 单份就够 ✓）＋ 送回去的落脚点 ✓ */
    private static volatile net.minecraft.nbt.CompoundTag STASH = null;
    private static volatile boolean stashLoaded = false;
    /** 「上一次站在**内陆格**」的位置 ✓ —— ★空岛乱 tp 会把人送进虚空✗★ ⇒ 只送回这种格 ✓ */
    private static final java.util.Map<String, double[]> LAST_SAFE =
            new java.util.concurrent.ConcurrentHashMap<>();

    /** ★"内陆格"：四邻**都能站**✗★（＝不是平台边 ✓；与 `platform` 的内陆定义同族 ✓） */
    private static boolean interior(ServerLevel lv, BlockPos feet) {
        if (!solidAt(lv, feet.below())) {
            return false;
        }
        int[][] d = {{1, 0}, {-1, 0}, {0, 1}, {0, -1}};
        for (int[] k : d) {
            BlockPos n = feet.offset(k[0], 0, k[1]);
            if (!passable2(lv, n) || !solidAt(lv, n.below())) {
                return false;
            }
        }
        return true;
    }

    private static void stashSave() {
        try {
            java.nio.file.Files.createDirectories(DEATH_STASH.getParent());
            net.minecraft.nbt.CompoundTag root = new net.minecraft.nbt.CompoundTag();
            if (STASH != null) {
                root.put("stash", STASH);
            }
            net.minecraft.nbt.NbtIo.writeCompressed(root, DEATH_STASH.toFile());
        } catch (Exception ignored) {
            // 死亡保险的落盘失败 ⇒ 家当只剩内存那一份 ⇒ 必须吵
            System.out.println("[dshbridge] stashSave FAILED (death stash not persisted) -> " + ignored);
        }
    }

    private static void stashLoad() {
        try {
            if (!java.nio.file.Files.isRegularFile(DEATH_STASH)) {
                return;
            }
            net.minecraft.nbt.CompoundTag root =
                    net.minecraft.nbt.NbtIo.readCompressed(DEATH_STASH.toFile());
            if (root.get("stash") instanceof net.minecraft.nbt.CompoundTag c) {
                STASH = c;
            }
        } catch (Exception ignored) {
            // 读不回来 ⇒ 还背包这一步会静默"还了个空" ⇒ 必须吵
            System.out.println("[dshbridge] stashLoad FAILED (death stash not restored) -> " + ignored);
        }
    }

    /** ★懒加载✗★ —— 与皮肤那份 `skins_state.json` **同一套做法** ✓（这文件里就这么干的 ✓） */
    private static void stashEnsure() {
        if (stashLoaded) {
            return;
        }
        stashLoaded = true;
        stashLoad();
    }

    private static void rememberSafeSpot(ServerPlayer p) {
        try {
            ServerLevel lv = lvl(p);
            if (p.onGround() && interior(lv, p.blockPosition())) {
                LAST_SAFE.put(WATCHED, new double[]{p.getX(), p.getY(), p.getZ()});
            }
        } catch (Exception ignored) {
        }
    }

    /** ★它回来了 ⇒ 把扣下的那一包**还回去** ＋ 送回安全落脚点**✗★ ✓ */
    private static void tryRestore(ServerPlayer p) {
        net.minecraft.nbt.CompoundTag tag = STASH;
        if (tag == null) {
            return;
        }
        String who = tag.getString("name");
        if (!p.getName().getString().equals(who)) {
            return;
        }
        try {
            var inv = p.getInventory();
            inv.clearContent();
            inv.load(tag.getList("items", 10));          // 10 = ListTag of CompoundTag ✓
            int back = 0;
            for (int i = 0; i < inv.getContainerSize(); i++) {
                if (!inv.getItem(i).isEmpty()) {
                    back += inv.getItem(i).getCount();
                }
            }
            boolean moved = false;
            if (tag.getBoolean("has_pos")) {
                p.teleportTo(tag.getDouble("x"), tag.getDouble("y"), tag.getDouble("z"));
                moved = true;
            }
            STASH = null;
            stashSave();
            ev("bot_revived", "phase=done who=" + esc(who) + " back_items=" + back
                    + (moved ? (" moved_to=" + String.format("%.0f,%.0f,%.0f",
                            tag.getDouble("x"), tag.getDouble("y"), tag.getDouble("z")))
                             : " moved_to=none"));
        } catch (Throwable ex) {
            // ★★v2.18.2：同样**不许静默**✗★（见 `onLivingDeath` 里那段理由 ✓）
            //   ⚠ 这一条比死亡那条**更要紧** ✗：★"还回去"失败 ⇒ 那包东西**只存在内存/盘里** ✗★
            //     ⇒ 不吭声 ⇒ 外面只会看到"背包空了" ✗ 却不知道为什么 ✓
            String msg = esc(ex.getClass().getSimpleName() + ": " + ex.getMessage());
            System.out.println("[dshbridge] death-insurance RESTORE FAILED -> " + msg);
            ev("bot_revived", "phase=error msg=" + msg);
        }
    }

    /** 档案里现在挂的是不是**我们要的那个**皮肤 ✓（对不上 ⇒ 该自愈 ✓） */
    private static boolean skinMatches(ServerPlayer p, String name) {
        Object[] e = SKINS.get(name);
        byte[] png = (e == null) ? null : (byte[]) e[0];
        if (png == null) {
            return false;
        }
        try {
            for (com.mojang.authlib.properties.Property pr : p.getGameProfile().getProperties().get("textures")) {
                String v = new String(java.util.Base64.getDecoder().decode(pr.getValue()),
                        java.nio.charset.StandardCharsets.UTF_8);
                if (v.contains("/skin/" + name + ".png")) {
                    return true;
                }
            }
        } catch (Exception ignored) {
        }
        return false;
    }

    /** ★自愈★ ✗：谁在记过皮肤的人里 ✓ 而档案对不上 ⇒ 重新注入 ✓（重生/重连/重启后自动长回来 ✓） */
    private static void skinSelfHeal(ServerLevel level) {
        if (SKIN_CHOSEN.isEmpty()) {
            return;
        }
        long now = level.getGameTime();
        if (wSkinCheck >= 0 && now - wSkinCheck < 100) {
            return;
        }
        wSkinCheck = now;
        if (SKINS.isEmpty()) {
            loadSkins();
        }
        if (SKIN_HTTP == null) {
            startSkinHttp();
        }
        for (java.util.Map.Entry<String, String> e : SKIN_CHOSEN.entrySet()) {
            try {
                ServerPlayer p = level.getServer().getPlayerList().getPlayerByName(e.getKey());
                if (p != null && !skinMatches(p, e.getValue())) {
                    if (applySkin(p, e.getValue())) {
                        ev("skin_heal", "player=" + e.getKey() + " skin=" + e.getValue());
                    }
                }
            } catch (Exception ignored) {
            }
        }
    }

    /** 把皮肤写进档案 ✓ 并**立刻**推给客户端 ✓（不然要重连才刷新 ✗） */
    private static boolean applySkin(ServerPlayer p, String name) {
        Object[] e = SKINS.get(name);
        if (e == null || e[0] == null) {
            return false;
        }
        try {
            String url = SKIN_BASE + "/skin/" + name + ".png?v=" + e[3] + "-"
                    + SKIN_SEQ.incrementAndGet();   // ★v2.12.2：内容指纹 ＋ 序号★ ✗ 强制重下 ✓
            String model = (String) e[2];
            String json = "{\"textures\":{\"SKIN\":{\"url\":\"" + url + "\",\"metadata\":{\"model\":\""
                    + model + "\"}}}}";
            String b64 = java.util.Base64.getEncoder().encodeToString(
                    json.getBytes(java.nio.charset.StandardCharsets.UTF_8));
            com.mojang.authlib.GameProfile prof = p.getGameProfile();
            prof.getProperties().removeAll("textures");
            prof.getProperties().put("textures",
                    new com.mojang.authlib.properties.Property("textures", b64));
            refreshSkinOnClient(p);
            return true;
        } catch (Exception ex) {
            return false;
        }
    }

    private static void clearSkin(ServerPlayer p) {
        try {
            p.getGameProfile().getProperties().removeAll("textures");
            refreshSkinOnClient(p);
        } catch (Exception ignored) {
        }
    }

    /** `/dskskin <text>` 一个贪心参数 ✓（list｜<名字> [玩家]｜off [玩家]｜base <url>｜reload ✓ 全 ASCII 回执 ✓） */
    private static int skinCmd(CommandContext<CommandSourceStack> ctx, String args)
            throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        if (SKINS.isEmpty()) {
            loadSkins();
            startSkinHttp();
        }
        String[] a = args == null ? new String[0] : args.trim().split("\\s+");
        String sub = a.length == 0 ? "list" : a[0].toLowerCase();
        if (sub.equals("reload")) {
            loadSkins();
            startSkinHttp();
            ok(src, "dskskin reload done count=" + SKINS.size() + " port=" + SKIN_PORT);
            return 1;
        }
        if (sub.equals("base")) {
            SKIN_BASE = a.length > 1 ? a[1] : null;
            ok(src, "dskskin base=" + (SKIN_BASE == null ? "(auto loopback)" : SKIN_BASE));
            return 1;
        }
        if (sub.equals("list")) {
            StringBuilder sb = new StringBuilder("dskskin count=" + SKINS.size()
                    + " base=" + (SKIN_BASE == null ? "-" : SKIN_BASE) + " port=" + SKIN_PORT + " ::");
            for (java.util.Map.Entry<String, Object[]> en : SKINS.entrySet()) {
                Object[] e = en.getValue();
                sb.append(' ').append(en.getKey()).append('[').append(e[2]).append(',')
                        .append(e[0] == null ? "BAD:" + e[4] : "ok").append(']');
            }
            ok(src, sb.toString());
            return 1;
        }
        ServerPlayer target;
        if (a.length > 1) {
            target = src.getServer().getPlayerList().getPlayerByName(a[1]);
            if (target == null) {
                bad(src, "dskskin: no such player " + a[1]);
                return 0;
            }
        } else {
            target = botPlayer();
            if (target == null) {
                bad(src, "dskskin: no fake player Bot (pass a player name)");
                return 0;
            }
        }
        if (sub.equals("off")) {
            clearSkin(target);
            ok(src, "dskskin off player=" + target.getName().getString());
            return 1;
        }
        if (!SKINS.containsKey(a[0])) {
            bad(src, "dskskin: unknown skin " + a[0] + " (try /dskskin list)");
            return 0;
        }
        if (!applySkin(target, a[0])) {
            Object[] e = SKINS.get(a[0]);
            bad(src, "dskskin: skin " + a[0] + " is not usable: "
                    + (e != null && e[4] != null ? String.valueOf(e[4]) : "unknown"));
            return 0;
        }
        skinStateLoad();
        SKIN_CHOSEN.put(target.getName().getString(), a[0]);
        skinStateSave();
        ok(src, "dskskin set=" + a[0] + " player=" + target.getName().getString()
                + " url=" + SKIN_BASE + "/skin/" + a[0] + ".png");
        return 1;
    }

    private static String idOf(ItemStack s) {
        return ForgeRegistries.ITEMS.getKey(s.getItem()).toString();
    }

    /** ★★v2.11.3：只读指令的"白名单"★★ ✗（用户指出的根因 ✓ 实测复现过两次 ✓）
     *
     *  <p>现象 ✗：只要**任何东西在轮询状态**（`talk.py` 每 2 秒 `dshevents` ✓ 我的检测脚本读状态 ✓）
     *  就会刷新 `LAST_CMD_TICK` ✓ ⇒ `isQuiet()`（安静 300 tick ＝ 15 秒）**永远达不到** ✗
     *  ⇒ **触发式反应一句都不会响** ✗✗（功能写了却等于没写 ✓ 最坏的一种错 ✗）
     *  <p>分流 ✓：下面这些"**只看不动**"的指令**不刷新** ✓
     *  ⇒ "安静"重新等于"**真的没人指挥它**" ✓ ⇒ 轮询与反应可以共存 ✓
     *  <p>判据用**回执的第一个词** ✓（`ok(src, "dshscan box=…")` 第一个词就是 `dshscan` ✓）
     *  ⇒ 于是**一行都不用改那十几个 handler** ✓
     */
    private static final java.util.Set<String> READONLY_CMDS = java.util.Set.of(
            "dshver", "dshdigest", "dshscan", "dshlook", "dshevents", "dshquiet", "dshstats",
            // ★2.56.0 新增的三条也只读 ✗ 别让"看状态"把安静门槛顶掉 ✓
            "dshhttp", "dshreqs", "dshyawprobe");

    private static boolean readonlyMsg(String s) {
        if (s == null) {
            return false;
        }
        int i = s.indexOf(' ');
        String head = (i < 0 ? s : s.substring(0, i)).trim();
        return READONLY_CMDS.contains(head);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // ★★2.46.0（§79.495）✗★★：**平滑转身 ＋ yaw 轨迹**
    //   ★用户口径✗★：★"★给转向一个速度：先加速 ✗ 中间匀速 ✗ 再减速★"✗★
    //   ★为什么必须模组做✗★：★N3 判据要 ≥20Hz 的 yaw 采样 ✗ 而桥每次往返 ~600ms✗★
    // ═══════════════════════════════════════════════════════════════════════
    static final double[] YAW_TRACE = new double[64];
    // ★2.47.0（§79.497）✗★：**只记转身那一段**（★长历史里 yaw 有别的抖动 ✗ 判不清✗★）
    static final double[] TURN_TRACE = new double[64];
    static int TURN_N = 0, TURN_AFTER = 0;
    static int YAW_N = 0, YAW_I = 0;
    // ★2.48.0（§79.499）✗★：**只观测** yaw 是谁改的（★不改行为✗★）
    //   ★★2.56.0（N3 定案）✗★★：原来是**一个全局** `PREV_END_YAW` ✗
    //     ⇒ 有第二个玩家（真人 Au_Sn 挂机）时，Bot 的 tick-start 会去和**上一个被 tick 的玩家**
    //       的 yaw 比 ⇒ ★每 tick 报一条假的 `yaw_write handler=external`✗★
    //     （历史"外部写者每 tick 把 Bot 掰 104°"就是这条假证据 ⇒ 见 tmp/ledger/mod-arch.md）
    //   ⇒ 现在**按玩家**各存一份 ✓ 判据才看得见真正的外部写 ✓
    static final Map<UUID, Double> PREV_END_YAW_BY = new ConcurrentHashMap<>();
    static long YAW_WRITES = 0L;
    static long YAW_EXTERNAL = 0L;
    static String YAW_LAST = "";

    static void probeYaw(ServerPlayer p, String handler, double before) {
        if (!watchedPlayer(p)) {
            return;                          // ★只看我们的身体 ✗ 别拿真人玩家当证据✗★
        }
        double now = p.getYRot();
        double d = now - before;
        if (Math.abs(d) < 0.01) {
            return;
        }
        YAW_WRITES++;
        YAW_LAST = handler + " " + String.format("%.1f", before)
                + "->" + String.format("%.1f", now)
                + " d=" + String.format("%.1f", d);
        ev("yaw_write", "handler=" + handler + " who=" + esc(p.getGameProfile().getName())
                + " before=" + String.format("%.1f", before)
                + " after=" + String.format("%.1f", now)
                + " d=" + String.format("%.1f", d));
    }

    /** ★2.56.0（N3）✗★：只对"我们那个身体"做朝向/转身/保持 ✗
     *  ★为什么✗★：原实现把 tickTurn/`reassertTurn`/`holdYaw` 跑在**所有玩家**上 ✗
     *  ⇒ 真人（Au_Sn）挂机时也会被按到 HOLD_YAW/turn 插值角上 ✗ —— 这是真 bug ✓（已修）
     */
    static boolean watchedPlayer(ServerPlayer p) {
        return p != null && p.getGameProfile() != null
                && p.getGameProfile().getName().equals(WATCHED);
    }

    static boolean TURN_ON = false;
    static float TURN_FROM = 0f, TURN_TO = 0f;
    static long TURN_START = 0L;
    static int TURN_TICKS = 8;

    /** ★梯形**位置**函数✗★：加速 25% ／ 匀速 50% ／ 减速 25% ⇒ 输出 0..1 */
    static double trapFraction(double u) {
        if (u <= 0.0) {
            return 0.0;
        }
        if (u >= 1.0) {
            return 1.0;
        }
        double a = 0.25;
        double area;
        if (u < a) {
            area = (u * u) / (2.0 * a);
        } else if (u < 1.0 - a) {
            area = a / 2.0 + (u - a);
        } else {
            double v = 1.0 - a;
            area = a / 2.0 + (v - a) + 1.0 - ((1.0 - u) * (1.0 - u)) / (2.0 * a);
        }
        return area / (1.0 - a);
    }

    /** 每 tick：记 yaw ＋ 若在转身就按梯形推进（★只改朝向 ✗ 不动世界✓★） */
    static void tickTurn(ServerPlayer p) {
        if (!watchedPlayer(p)) {
            return;                          // ★只转我们的身体✗★（真人挂机时不许被插值角按头 ✓）
        }
        double y = p.getYRot();
        // ★转身专用轨迹✗★：转的期间每 tick 都记 ✗ 转完再记 3 个样本（★看得见减速收尾✗★）
        if (TURN_ON || TURN_AFTER > 0) {
            if (TURN_N < TURN_TRACE.length) {
                TURN_TRACE[TURN_N++] = y;
            }
            if (!TURN_ON && TURN_AFTER > 0) {
                TURN_AFTER--;
            }
        }
        YAW_TRACE[YAW_I] = y;
        YAW_I = (YAW_I + 1) % YAW_TRACE.length;
        if (YAW_N < YAW_TRACE.length) {
            YAW_N++;
        }
        if (!TURN_ON) {
            return;
        }
        long now = p.level().getGameTime();
        double u = (now - TURN_START) / (double) Math.max(1, TURN_TICKS);
        if (u >= 1.0) {
            p.setYRot(TURN_TO);
            p.yRotO = TURN_TO;
            p.yHeadRot = TURN_TO;
            p.yHeadRotO = TURN_TO;
            p.yBodyRot = TURN_TO;
            p.yBodyRotO = TURN_TO;
            TURN_ON = false;
            HOLD_YAW = TURN_TO;         // ★2.50.0✗★ 转完之后**保持这个朝向**
            TURN_AFTER = 3;
            StringBuilder tb = new StringBuilder();
            for (int k = 0; k < TURN_N; k++) {
                if (k > 0) {
                    tb.append(",");
                }
                tb.append(String.format("%.1f", TURN_TRACE[k]));
            }
            ev("turn_trace", "n=" + TURN_N + " vals=" + tb);
            ev("turn_done", "to=" + String.format("%.1f", TURN_TO)
                    + " ticks=" + TURN_TICKS);
            return;
        }
        float yaw = (float) (TURN_FROM + (TURN_TO - TURN_FROM) * trapFraction(u));
        p.setYRot(yaw);
        p.yRotO = yaw;
        p.yHeadRot = yaw;
        p.yHeadRotO = yaw;
        p.yBodyRot = yaw;
        p.yBodyRotO = yaw;
    }

    /** ★2.49.0（§79.502）✗★：**tick 末尾重申朝向**（★我们后写 ⇒ 覆盖别人那一笔✗★）
     *
     * ★为什么要它✗★：★2.48.0 探针证明 —— 每 tick 有个 `external` 写者把我们设的角改掉
     *   （★-69.1 ↔ 34.9 每 tick 交替 ✗ 差 104°✗★）⇒ 视觉上就是**抽搐** ✗ N3 判据拒绝的就是这个 ✓
     * ★我们删不掉别人的写 ✗ 但可以**写得比它晚**✗★ ✓
     */
    // ★★2.50.0（§79.502）✗★★：**保持朝向**
    //   ★为什么必须有它✗★：★实测 `external` 写者**每 tick 都抢**（★连不转身时也抢✗★）
    //     ⇒ 我们删不掉它 ⇒ 只能**在 tick 的最末尾**再写一次（★ServerTickEvent.END ✗ 所有玩家 tick 之后✗★）
    static boolean HOLD_ON = true;
    static double HOLD_YAW = Double.NaN;
    static long HOLD_FIXES = 0L;

    /** 在 tick 最末尾把朝向按回 HOLD_YAW（★只在真的被改过时才动 ＋ 才记✗★） */
    // ★★2.51.0（§79.505）✗★★：**分段夹逼** —— 写发生在 tick 的哪一段
    //   ★2.56.0：改成**按玩家**记录 ✗（原来全局一份 ⇒ 两个玩家时"上一段"是别人的角 ✗ 假证据 ✓）
    static final Map<UUID, String> BRACKET_TAG_BY = new ConcurrentHashMap<>();
    static final Map<UUID, Double> BRACKET_YAW_BY = new ConcurrentHashMap<>();
    static volatile String BRACKET_LAST_TAG = "";
    static int BRACKET_N = 0;
    static final String[] BRACKET_LOG = new String[10];

    /** 在每个钩子上打一个"戳"：值变了就记一条 `yaw_bracket at=<本段> prev=<上段> d=<度>` */
    static void bracket(ServerPlayer p, String tag) {
        if (p == null) {
            return;
        }
        double y = p.getYRot();
        UUID id = p.getUUID();
        Double prevY = BRACKET_YAW_BY.get(id);
        String prevTag = BRACKET_TAG_BY.getOrDefault(id, "");
        if (prevY != null) {
            double d = y - prevY;
            while (d > 180.0) {
                d -= 360.0;
            }
            while (d < -180.0) {
                d += 360.0;
            }
            if (Math.abs(d) >= 0.01) {
                BRACKET_N++;
                String line = "who=" + esc(p.getGameProfile().getName())
                        + " at=" + tag + " prev=" + prevTag
                        + " from=" + String.format("%.1f", prevY)
                        + " to=" + String.format("%.1f", y)
                        + " d=" + String.format("%.1f", d);
                synchronized (BRACKET_LOG) {
                    BRACKET_LOG[BRACKET_N % BRACKET_LOG.length] = line;
                }
                ev("yaw_bracket", line);
            }
        }
        BRACKET_TAG_BY.put(id, tag);
        BRACKET_YAW_BY.put(id, y);
        BRACKET_LAST_TAG = tag;
    }

    static void holdYaw(ServerPlayer p) {
        if (!watchedPlayer(p)) {
            return;                          // ★只保持我们的朝向✗★（别把真人的视角也按住 ✓）
        }
        if (!HOLD_ON || Double.isNaN(HOLD_YAW)) {
            return;
        }
        double want = HOLD_YAW;
        if (TURN_ON) {
            long now = p.level().getGameTime();
            double u = (now - TURN_START) / (double) Math.max(1, TURN_TICKS);
            want = (u >= 1.0) ? TURN_TO
                    : (TURN_FROM + (TURN_TO - TURN_FROM) * trapFraction(u));
            HOLD_YAW = want;
        }
        float have = p.getYRot();
        double d = want - have;
        while (d > 180.0) {
            d -= 360.0;
        }
        while (d < -180.0) {
            d += 360.0;
        }
        if (Math.abs(d) < 0.01) {
            return;
        }
        float y = (float) want;
        p.setYRot(y);
        p.yRotO = y;
        p.yHeadRot = y;
        p.yHeadRotO = y;
        p.yBodyRot = y;
        p.yBodyRotO = y;
        HOLD_FIXES++;
        ev("turn_hold", "have=" + String.format("%.1f", have)
                + " want=" + String.format("%.1f", want)
                + " d=" + String.format("%.1f", d) + " n=" + HOLD_FIXES);
    }

    private static int holdCmd(CommandContext<CommandSourceStack> ctx, boolean on) {
        CommandSourceStack src = ctx.getSource();
        HOLD_ON = on;
        if (on && Double.isNaN(HOLD_YAW)) {
            try {
                HOLD_YAW = src.getPlayerOrException().getYRot();
            } catch (Exception exc) {       // ★不许静默✗★
                ev("turn_hold", "reason=no_player");
            }
        }
        ok(src, "dshhold on=" + HOLD_ON + " yaw="
                + (Double.isNaN(HOLD_YAW) ? "nan" : String.format("%.1f", HOLD_YAW))
                + " fixes=" + HOLD_FIXES);
        return 1;
    }

    static void reassertTurn(ServerPlayer p) {
        if (!TURN_ON || !watchedPlayer(p)) {
            return;
        }
        long now = p.level().getGameTime();
        double u = (now - TURN_START) / (double) Math.max(1, TURN_TICKS);
        float want = (u >= 1.0) ? TURN_TO
                : (float) (TURN_FROM + (TURN_TO - TURN_FROM) * trapFraction(u));
        float have = p.getYRot();
        float d = want - have;
        while (d > 180f) {
            d -= 360f;
        }
        while (d < -180f) {
            d += 360f;
        }
        if (Math.abs(d) < 0.01f) {
            return;                       // ★没人动过 ✗ 不用记（★免得刷屏✗★）
        }
        p.setYRot(want);
        p.yRotO = want;
        p.yHeadRot = want;
        p.yHeadRotO = want;
        p.yBodyRot = want;
        p.yBodyRotO = want;
        ev("turn_reassert", "have=" + String.format("%.1f", have)
                + " want=" + String.format("%.1f", want)
                + " d=" + String.format("%.1f", d));
    }

    private static int turnStart(CommandContext<CommandSourceStack> ctx, float deg, int ticks)
            throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        ServerPlayer p = src.getPlayerOrException();
        float from = p.getYRot();
        float to = from + deg;
        while (to > 180f) {
            to -= 360f;
        }
        while (to < -180f) {
            to += 360f;
        }
        TURN_FROM = from;
        TURN_TO = to;
        TURN_START = p.level().getGameTime();
        TURN_TICKS = ticks > 0 ? ticks : Math.max(4, Math.min(30, (int) (Math.abs(deg) / 12.0)));
        TURN_ON = true;
        TURN_N = 0;
        TURN_AFTER = 3;
ev("turn_start", "from=" + String.format("%.1f", from)
                + " to=" + String.format("%.1f", to) + " ticks=" + TURN_TICKS);
        ok(src, "dshturn from=" + String.format("%.1f", from)
                + " to=" + String.format("%.1f", to) + " ticks=" + TURN_TICKS);
        return 1;
    }

    private static int yawTrace(CommandContext<CommandSourceStack> ctx, int n)
            throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        ServerPlayer p = src.getPlayerOrException();
        if (TURN_N > 2) {
            StringBuilder ss = new StringBuilder();
            for (int k = 0; k < TURN_N; k++) {
                if (k > 0) {
                    ss.append(",");
                }
                ss.append(String.format("%.1f", TURN_TRACE[k]));
            }
            ok(src, "dshyawtrace n=" + TURN_N + " src=turn tick=" + p.level().getGameTime()
                    + " yaw_now=" + String.format("%.1f", p.getYRot())
                    + " writes=" + YAW_WRITES + " last=[" + YAW_LAST + "]"
                    + " vals=" + ss);
            return 1;
        }
        int have = Math.min(n, YAW_N);
        StringBuilder sb = new StringBuilder();
        // 从"最老的那个"开始列，保证时序
        int start = (YAW_I - have + YAW_TRACE.length * 2) % YAW_TRACE.length;
        for (int k = 0; k < have; k++) {
            int idx = (start + k) % YAW_TRACE.length;
            if (k > 0) {
                sb.append(",");
            }
            sb.append(String.format("%.1f", YAW_TRACE[idx]));
        }
        ok(src, "dshyawtrace n=" + have + " tick=" + p.level().getGameTime()
                + " yaw_now=" + String.format("%.1f", p.getYRot()) + " vals=" + sb);
        return 1;
    }

    // ══════════════════════════════════════════════════════════════════════════
    // ★★★2.56.0（N3）✗★★★ **一次性 yaw 写者探针**（`/dshyawprobe ...`）
    //   要复核的历史结论："每 tick 有个**非本模组的写者**把 Bot 朝向改成固定角、
    //   与目标差 ~104°、发生在 ServerTickEvent.END 之后；HOLD_YAW 只把 40 次压到 7 次"。
    //   2026-11-02 对 2.55.1 的现场实测指向另一解释：`PREV_END_YAW`/`BRACKET_*` 是**全局一份** ✗
    //   ⇒ 场上有第二个玩家（真人 Au_Sn 挂机）时，Bot 的 tick-start 跟**别人的** yaw 比 ⇒ 假 external ✓
    //   （现场值：Bot yaw 与 Au_Sn yaw 差 49°；历史 104° 同样是两个人的差 ✗）
    //   ⇒ 本探针**按玩家**判 ＋ 记相位（BRACKET_LAST_TAG）＋ 抓"栈里带 Rot 的线程"证据 ✓
    //   产出：`logs/yawprobe.log`（持久）＋ `/dshyawprobe report`（一行摘要，进判据）✓
    //   ★默认关✗★；`/dshyawprobe bus` 另列 tick 事件监听者（谁可能写 yaw 的候选）✓
    // ══════════════════════════════════════════════════════════════════════════
    static volatile boolean YAWP_ON = false;
    static Thread YAWP_THREAD = null;
    static ServerPlayer YAWP_PLAYER = null;
    static volatile int YAWP_LIMIT = 0;
    static volatile long YAWP_TICK0 = 0L;
    static volatile int YAWP_SAMPLES = 0;
    static volatile int YAWP_CHANGES = 0;
    static volatile String YAWP_LAST_LINE = "";
    static volatile long YAWP_EXTERNAL0 = 0L;
    static final java.util.ArrayDeque<String> YAWP_LINES = new java.util.ArrayDeque<>();
    static final Object YAWP_LOCK = new Object();
    static java.io.PrintWriter YAWP_OUT = null;

    static void yawpRec(String line) {
        synchronized (YAWP_LOCK) {
            YAWP_LINES.addLast(line);
            while (YAWP_LINES.size() > 200) {
                YAWP_LINES.removeFirst();
            }
            YAWP_LAST_LINE = line;
            if (YAWP_OUT != null) {
                YAWP_OUT.println(line);
                YAWP_OUT.flush();
            }
        }
    }

    /** 采样线程：每 ~2ms 读一次 Bot yaw；变了就记相位 ＋ "栈里带 Rot 的线程"（抓写者）✓ */
    static void yawpLoop() {
        double last = Double.NaN;
        int stackBudget = 40;
        while (YAWP_ON) {
            try {
                ServerPlayer p = YAWP_PLAYER;
                if (p == null || p.isRemoved()) {
                    yawpRec("player_gone");
                    break;
                }
                if (YAWP_LIMIT > 0 && TICK_COUNT.get() - YAWP_TICK0 >= YAWP_LIMIT) {
                    break;
                }
                YAWP_SAMPLES++;
                double y = p.getYRot();
                if (Double.isNaN(last)) {
                    last = y;
                } else if (Math.abs(y - last) > 0.01) {
                    YAWP_CHANGES++;
                    StringBuilder sb = new StringBuilder("change n=" + YAWP_CHANGES
                            + " tick=" + p.level().getGameTime()
                            + " prev=" + String.format("%.1f", last)
                            + " now=" + String.format("%.1f", y)
                            + " phase=" + BRACKET_LAST_TAG);
                    if (stackBudget-- > 0) {
                        sb.append(yawpStacks());
                    }
                    yawpRec(sb.toString());
                    last = y;
                }
                Thread.sleep(2L);
            } catch (InterruptedException ie) {
                Thread.currentThread().interrupt();
                break;
            } catch (Throwable th) {
                yawpRec("error=" + th.getClass().getSimpleName());
                break;
            }
        }
        YAWP_ON = false;
        YAWP_PLAYER = null;
        synchronized (YAWP_LOCK) {
            if (YAWP_OUT != null) {
                YAWP_OUT.close();
                YAWP_OUT = null;
            }
        }
        YAWP_THREAD = null;
        yawpRec("stopped samples=" + YAWP_SAMPLES + " changes=" + YAWP_CHANGES
                + " external_events=" + (YAW_EXTERNAL - YAWP_EXTERNAL0));
    }

    /** 抓"栈里带 Rot/Yaw 的线程"的浅栈（★只在变化时抓 ✗ 有预算 ✓ 抓不到也不编✗★） */
    static String yawpStacks() {
        StringBuilder sb = new StringBuilder();
        try {
            for (java.util.Map.Entry<Thread, StackTraceElement[]> en
                    : Thread.getAllStackTraces().entrySet()) {
                StackTraceElement[] st = en.getValue();
                boolean rot = false;
                for (StackTraceElement el : st) {
                    String m = el.getMethodName();
                    if (m.contains("Rot") || m.contains("Yaw")) {
                        rot = true;
                        break;
                    }
                }
                if (!rot) {
                    continue;
                }
                sb.append(" | th=").append(en.getKey().getName());
                int k = 0;
                for (StackTraceElement el : st) {
                    if (el.getClassName().startsWith("com.dsh.bridge")) {
                        break;
                    }
                    sb.append(" <-").append(el.getClassName()).append('.').append(el.getMethodName());
                    if (++k >= 8) {
                        break;
                    }
                }
            }
        } catch (Throwable th) {
            sb.append(" stack_failed=").append(th.getClass().getSimpleName());
        }
        return sb.toString();
    }

    static void yawpStop() {
        boolean was = YAWP_ON;
        YAWP_ON = false;
        Thread t = YAWP_THREAD;
        if (t != null) {
            t.interrupt();
        }
        YAWP_THREAD = null;
        YAWP_PLAYER = null;
        synchronized (YAWP_LOCK) {
            if (YAWP_OUT != null) {
                YAWP_OUT.close();
                YAWP_OUT = null;
            }
        }
        if (was) {
            yawpRec("stopped_manual samples=" + YAWP_SAMPLES + " changes=" + YAWP_CHANGES);
        }
    }

    static int yawpStart(CommandContext<CommandSourceStack> ctx, int ticks) {
        ServerPlayer p = ctx.getSource().getServer().getPlayerList().getPlayerByName(WATCHED);
        if (p == null) {
            bad(ctx.getSource(), "dshyawprobe reason=no_bot");
            return 0;
        }
        yawpStop();
        YAWP_PLAYER = p;
        YAWP_TICK0 = TICK_COUNT.get();
        YAWP_LIMIT = ticks;
        YAWP_SAMPLES = 0;
        YAWP_CHANGES = 0;
        YAWP_EXTERNAL0 = YAW_EXTERNAL;
        synchronized (YAWP_LOCK) {
            YAWP_LINES.clear();
            try {
                java.nio.file.Path log = java.nio.file.Paths.get("logs", "yawprobe.log");
                java.nio.file.Path parent = log.toAbsolutePath().getParent();
                if (parent != null) {
                    java.nio.file.Files.createDirectories(parent);
                }
                YAWP_OUT = new java.io.PrintWriter(java.nio.file.Files.newBufferedWriter(log,
                        java.nio.charset.StandardCharsets.UTF_8,
                        java.nio.file.StandardOpenOption.CREATE,
                        java.nio.file.StandardOpenOption.APPEND), true);
                YAWP_OUT.println("=== yawprobe start tick=" + p.level().getGameTime()
                        + " who=" + p.getGameProfile().getName() + " ticks=" + ticks
                        + " hold=" + HOLD_ON + " hold_yaw="
                        + (Double.isNaN(HOLD_YAW) ? "nan" : String.format("%.1f", HOLD_YAW))
                        + " yaw0=" + String.format("%.1f", p.getYRot()));
            } catch (Exception exc) {
                YAWP_OUT = null;
                yawpRec("log_failed reason=" + exc.getClass().getSimpleName());
            }
        }
        YAWP_ON = true;
        Thread th = new Thread(DshBridgeMod::yawpLoop, "dsh-yaw-probe");
        th.setDaemon(true);
        YAWP_THREAD = th;
        th.start();
        ok(ctx.getSource(), "dshyawprobe state=started ticks=" + ticks
                + " who=" + p.getGameProfile().getName() + " log=logs/yawprobe.log");
        return 1;
    }

    static int yawpReport(CommandContext<CommandSourceStack> ctx) {
        StringBuilder sb = new StringBuilder("dshyawprobe state=" + (YAWP_ON ? "on" : "off")
                + " ticks=" + (TICK_COUNT.get() - YAWP_TICK0)
                + " samples=" + YAWP_SAMPLES + " changes=" + YAWP_CHANGES
                + " external_events=" + (YAW_EXTERNAL - YAWP_EXTERNAL0)
                + " hold=" + HOLD_ON + " hold_yaw="
                + (Double.isNaN(HOLD_YAW) ? "nan" : String.format("%.1f", HOLD_YAW)));
        List<String> lines = new ArrayList<>();
        synchronized (YAWP_LOCK) {
            lines.addAll(YAWP_LINES);
        }
        int show = Math.min(8, lines.size());
        for (int i = lines.size() - show; i < lines.size(); i++) {
            sb.append(" | ").append(lines.get(i));
        }
        ok(ctx.getSource(), sb.toString());
        return 1;
    }

    /** 列出 tick 事件监听者（★只读✗★）：谁在 tick 里跑 ⇒ 谁可能是 yaw 写者候选 ✓ */
    static int yawpBus(CommandContext<CommandSourceStack> ctx) {
        StringBuilder sb = new StringBuilder("dshyawprobe bus");
        try {
            Object bus = net.minecraftforge.common.MinecraftForge.EVENT_BUS;
            sb.append(" cls=").append(bus.getClass().getName());
            java.lang.reflect.Field idf = bus.getClass().getDeclaredField("busID");
            idf.setAccessible(true);
            int busId = idf.getInt(bus);
            for (Class<?> ec : new Class<?>[]{TickEvent.ServerTickEvent.class,
                    TickEvent.PlayerTickEvent.class}) {
                net.minecraftforge.eventbus.ListenerList ll =
                        net.minecraftforge.eventbus.api.EventListenerHelper.getListenerList(ec);
                net.minecraftforge.eventbus.api.IEventListener[] arr = ll.getListeners(busId);
                sb.append(" | ").append(ec.getSimpleName()).append(" total=").append(arr.length);
                int shown = 0;
                for (int i = 0; i < arr.length && shown < 12; i++) {
                    String s = String.valueOf(arr[i]);
                    if (!s.contains("TickEvent")) {
                        continue;
                    }
                    sb.append("; ").append(i).append('=').append(s.length() > 120 ? s.substring(0, 120) : s);
                    shown++;
                }
            }
        } catch (Throwable th) {
            sb.append(" failed=").append(th.getClass().getSimpleName())
                    .append(':').append(String.valueOf(th.getMessage()));
        }
        yawpRec(sb.toString());
        ok(ctx.getSource(), sb.toString());
        return 1;
    }

    // ══════════════════════════════════════════════════════════════════════════
    // ★★2.53.0（§79.513）✗★★ **直连**: the mod serves a tiny HTTP endpoint itself
    //   ★用户口径✗★：「后续应当简化该流程，能不能优化成**直连**」
    //   ★动机✗★：★CC 计算机是**又一个会坏掉的中间件** —— 2026-11-01 一次 fill 把它填掉
    //     ⇒ 整套系统当场断线 ⇒ **少一个环节就少一个故障点** ✓
    //   ★协议（★刻意最简✗★）✗★：
    //     POST /cmd     body = 指令原文（UTF-8）⇒ 回模组的回执文本
    //     GET  /health  ⇒ "ok v…"
    //   ★纪律✗★：指令**必须在服务器线程执行** ✗ HTTP 线程只收发 ✓
    // ══════════════════════════════════════════════════════════════════════════
    // ══════════════════════════════════════════════════════════════════════════
    // ★★2.57.0（A2/S1 结构第二刀）✗★★：**HTTP 服务边界已搬出主类** ⇒ `com.dsh.bridge.HttpBridge`
    //   ★只搬不改✗★：accept 池／单线程世界车道／token／Origin／/raw 白名单／请求账本／
    //                 dshhttp／dshreqs／httpRunRaw／httpRunCommand **逐行搬到 HttpBridge.java** 了 ✓
    //                 逻辑/回执文本/tick 顺序一字未动 ✓（S1 判据：tools/mod_arch_test.py X1~X7）
    //   ★为什么事件出口留在这里✗★：`errata_guard_test` 的 E11 只扫**本文件**对账事件名 ✗
    //     ⇒ 把 `ev("http_server"/"http_error")` 字面量搬走会让 E11 报"漏掉 2 个"✗
    //     ⇒ 主类保留两个一行转发（`httpEventServer`/`httpEventError`）✓ E11 仍全绿 ✓
    // ══════════════════════════════════════════════════════════════════════════

    /** S1：HTTP 层的两个事件出口（★字面量必须留在本文件 ✗ 见上✗★） */
    static void httpEventServer(String data) {
        ev("http_server", data);
    }

    static void httpEventError(String data) {
        ev("http_error", data);
    }

    static void ok(CommandSourceStack src, String msg) {
        // ★每个回执都顺手记一笔"刚有指令" ✗ —— 空闲看四周靠它避开"正在干活"✗（见 AUTO_IDLE ✓）
        // ⚠ v2.11.3：**只读指令除外** ✗ —— 不然"轮询状态"会把安静门槛永远顶掉 ✓（见 READONLY_CMDS ✓）
        if (!readonlyMsg(msg)) {
            LAST_CMD_TICK = src.getLevel().getGameTime();
        }
        src.sendSuccess(() -> Component.literal(msg), false);
    }

    private static void bad(CommandSourceStack src, String msg) {
        if (!readonlyMsg(msg)) {
            LAST_CMD_TICK = src.getLevel().getGameTime();
        }
        src.sendFailure(Component.literal(msg));
    }

    /** 记一条事件 ✓（`/dshevents [since]` 增量取走 ✓ 全 ASCII ✗ 见纪律③ ✓）
     *  ★A7✗★：若当前有 HTTP 请求在上（REQ_CTX）⇒ 行尾追加 ` req=r<N>` ✓
     *   ★只在有请求时追加✗★ ⇒ 原来的 `#seq kind data` 读法一字不变 ✓（events_log/exec3d 都验过）
     */
    static void ev(String kind, String data) {
        String req = REQ_CTX.get();
        String line = "#" + EVENT_SEQ.incrementAndGet() + " " + kind + " " + data
                + (req == null ? "" : " req=" + req);
        synchronized (EVENTS) {
            EVENTS.addLast(line);
            while (EVENTS.size() > EVENT_KEEP) {
                EVENTS.removeFirst();
            }
        }
        react(kind, data);                       // ★v2.11：触发式反应 ✓（挂在这一个出口上 ✓）
    }

    /** ★★v2.28（§79.412）✗★★：★**写操作发一条 `mut`**（★世界变了 ✗ 让外面不必靠"重新扫"猜✗★）✗★
     *
     *  ★格式✗★：★`mut pos=x,y,z was=<旧> now=<新>`**（★`#<seq>` 由 `ev()` 自带✗★）✗★
     *  ★为什么✗★：★§79.406 的"★放成功了却不记账 ⇒ --restore 漏拆★"** ✗★
     *    ★根就是"★模组不告诉外面它改了什么★" ⇒ ★这一条事件把这个缺口补上**✗★ ✓
     */
    private static void evMut(BlockPos pos, String was, String now) {
        if (was != null && was.equals(now)) {
            return;                       // ★没变就不报 ✗ 免得噪声✗★
        }
        ev("mut", "pos=" + pos.getX() + "," + pos.getY() + "," + pos.getZ()
                + " was=" + (was == null ? "?" : was)
                + " now=" + (now == null ? "?" : now));
    }


    // ══ ★★v2.11：触发式反应（用户要求 ✓「受击之后会做什么、说什么；捡到东西；没捡到东西」）★★ ══
    //
    // 设计四条（每条都有理由 ✗）：
    //  ① **挂在 `ev()` 这唯一出口上** ✓ —— 全模组所有事件都从这里过 ✓
    //     ⇒ 只改一处 ✓ 而且**以后新加的事件自动也会被它看见** ✓
    //  ② ★复用现成的两道闸★ ✗：`HUMANOID`（`/dshidle off` 一键闭嘴 ✓）＋
    //     `isQuiet()`（最近 15 秒没有模组指令 ✓）
    //     ⇒ **智能体正在干活时（每秒都有指令 ✓）它绝不会插嘴** ✓✓
    //       这一点是要命的 ✓：作业中间冒一句"哎！"会把 harness 的节奏和聊天都搅乱 ✗
    //  ③ **限流** ✗：两条之间至少 5 秒 ✓ 每 60 秒最多 6 条 ✓（现在只有 6~8 句台词 ✓
    //     不刷屏 ✗ 也不至于像复读机 ✓）
    //  ④ ★只说**能确证**的事★ ✗：`inv` 事件里**没有物品名** ✓（只有 delta 件数 ✓）
    //     ⇒ 就只说"多了/少了"✓ **绝不编"捡到了铁"** ✗（本项目最恨编造 ✓）
    private static final String[] HURT_LINES = {"哎！", "谁打我？", "打我干嘛。", "疼。"};
    private static final String[] LOWHP_LINES = {"血不多了，躲躲。", "再来一下就没了。"};
    // ★★v2.11.1：按**受击来源**分台词★★ ✗（用户抓到的真错误 ✓）
    //   原来只读 `hp=` ✗ 完全忽略 `src=` ✗ ⇒ **溺水也喊"谁打我？"** ✗ —— 当场说错话 ✓
    //   实测证据 ✓（本会话真实事件 ✓ 不是推测）：`#137 damage hp=14.0 delta=-0.5 src=drown`
    //     hp=14 > 8 ⇒ 走 HURT_LINES ⇒ 它在水里喊"谁打我？"✗ ★正是本项目最恨的**编造**★ ✗
    //   ⚠ 用户还提醒了一条 ✓：**别拿 `delta=` 当受击量** ✗ —— 它会被采样窗口里的**回血**污染 ✓
    //     （那条 `delta=-0.5` 就不是干净的一击 ✓）⇒ 现在代码没这么用 ✓ 也别以后这么用 ✗
    private static final String[] DROWN_LINES = {"差点栽水里。", "呛到了。", "得上去换口气。"};
    private static final String[] FALL_LINES = {"摔得够呛。", "哎哟，这下摔重了。", "腿软了。"};
    private static final String[] STARVE_LINES = {"饿得慌。", "肚子空了。", "得找点吃的。"};
    private static final String[] BURN_LINES = {"烫！", "着火了！", "烧到了。"};
    /** 说不清来源时**只喊疼** ✓ —— 绝不猜"谁打我" ✗ */
    private static final String[] PAIN_LINES = {"疼。", "嘶…", "哎哟。"};
    private static final String[] GOT_LINES = {"收下了。", "捡到了。", "嗯，多了点东西。"};
    private static final String[] LOST_LINES = {"我东西呢？", "欸，少了一件。", "别是丢了吧…"};
    private static final String[] EXPIRE_LINES = {"地上那个快没了，我去捡。", "那东西要消失了，我去拿。"};
    /** ★没空位时的版本★ ✗ —— 用户抓到的第二条真错误 ✓：
     *  原来只有"我去捡"✗ 那是**承诺动作** ✓ 而模组自己在同一条事件里就写着
     *  `(pickup needs a FREE SLOT - see inv_guard)` ✓ ⇒ 捡起来要**空位** ✓
     *  而现状恰好 `free=0` ✗ ⇒ 那句**必假** ✗（既骗了人 ✓ 也骗了它自己 ✓）
     *  ⇒ 现在按"到底有没有空位"分两套 ✓：**有空位才敢承诺** ✗ */
    private static final String[] NO_ROOM_LINES = {"地上那个快没了，可我包里没空位。", "那东西要消失了，我塞不下。"};

    /** 空位有几个 ✓（36 格主背包 ✓ 不含护甲/副手 ✓）—— 用来决定"能不能承诺去捡"✗ */
    private static int freeSlots(ServerPlayer p) {
        int n = 0;
        try {
            for (int i = 0; i < 36; i++) {
                if (p.getInventory().getItem(i).isEmpty()) {
                    n++;
                }
            }
        } catch (Exception ignored) {
            return 0;                              // 读不到 ⇒ 当没有空位 ✓（保守 ✓ 不空口承诺 ✗）
        }
        return n;
    }
    private static final String[] CREATIVE_LINES = {"我怎么变创造了？", "这模式不对吧。"};
    private static final String[] WARP_LINES = {"我怎么被挪地方了？", "刚才是被传送了？"};
    private static final String[] ATE_LINES = {"吃饱了。", "嗯，垫了一下。"};
    private static final String[] XP_LINES = {"升级了？", "经验涨了。"};
    private static long LAST_REACT_TICK = 0;
    private static int REACT_COUNT = 0;
    private static long REACT_WINDOW_START = 0;
    private static final long REACT_GAP_TICKS = 100;      // 两条之间 ≥5 秒 ✓
    private static final int REACT_MAX_PER_WINDOW = 6;    // 每 60 秒最多 6 条 ✓
    private static final long REACT_WINDOW_TICKS = 1200;

    /** 假人本体 ✓（事件里没带玩家 ⇒ 按名字找 ✓ 找不到就**不反应**✗ 绝不猜 ✓） */
    private static ServerPlayer botPlayer() {
        try {
            var srv = net.minecraftforge.server.ServerLifecycleHooks.getCurrentServer();
            if (srv == null) {
                return null;
            }
            return srv.getPlayerList().getPlayerByName(WATCHED);
        } catch (Exception e) {
            return null;
        }
    }

    private static String pick(String[] arr) {
        return arr[(int) (Math.random() * arr.length)];
    }

    /** ★"安静探针"★ ✗ —— 读一眼状态，但**绝不刷新** `LAST_CMD_TICK` ✓
     *
     *  <p>为什么要专门开一个 ✗（用户发现的副作用 ✓）：
     *  `ok()` / `bad()` 都会刷新 `LAST_CMD_TICK` ✓ ⇒ 保活探针会把"安静 300 tick"永远顶掉 ✗
     *  ⇒ 于是 v2.11 的反应**一句都不会响** ✗（功能写了却等于没写 ✓ 最坏的一种错 ✗）
     *  ⇒ 所以这条指令**直接 `sendSuccess`**（不走 `ok()` ✓）⇒ 看得到状态 ✓ 却不算"有人指挥它" ✓
     *  <p>用法 ✓：`/dshquiet` 只看 ✓ ｜ `/dshquiet canned off` 顺手把 canned 快嘴关掉 ✓（让 LLM 当唯一声音 ✓）
     */
    /** ★★v2.13：`/dshdrop [半径]`★★ ✗（用户实测："看不太到水下的掉落物" ✓）
     *
     *  <p>为什么必须有它 ✗：模组里原本**只有**一条"快消失时才报警"的扫描 ✓
     *  （`left &lt; 600` 才发事件 ✓）⇒ 平时**根本问不出"附近有什么掉落物"** ✗
     *  而 `dshdigest` 里的 `drops=` 又是**另一套盒子** ✗ ⇒ 两处口径不一致 ⇒ 更看不清 ✓
     *  <p>⇒ 本指令**逐条列出**：id ✓ 物品 ✓ 数量 ✓ 坐标 ✓ 距离 ✓ 剩余秒 ✓ ★在不在水里★ ✓
     *  回执**全 ASCII** ✓（CC 通道不吃非 ASCII ✓ P13 ✓）
     */
    private static int dropList(CommandContext<CommandSourceStack> ctx, double radius)
            throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        ServerPlayer p = src.getPlayerOrException();
        ServerLevel level = lvl(p);
        if (level == null) {
            bad(src, "dshdrop: no level");
            return 0;
        }
        AABB box = p.getBoundingBox().inflate(Math.max(1.0, Math.min(48.0, radius)));
        java.util.List<Entity> found = level.getEntities(p, box, x -> x instanceof ItemEntity);
        StringBuilder sb = new StringBuilder();
        int n = 0, inWater = 0;
        java.util.List<Entity> sorted = new java.util.ArrayList<>(found);
        sorted.sort(java.util.Comparator.comparingDouble(p::distanceTo));
        for (Entity en : sorted) {
            ItemEntity ie = (ItemEntity) en;
            if (n >= 24) {
                break;
            }
            boolean wet = ie.isInWater();
            if (wet) {
                inWater++;
            }
            double d = p.distanceTo(ie);
            sb.append(n == 0 ? " " : " | ").append("id=").append(ie.getId())
                    .append(" item=").append(idOf(ie.getItem()))
                    .append(" x").append(ie.getItem().getCount())
                    .append(" at=").append(String.format("%.1f,%.1f,%.1f", ie.getX(), ie.getY(), ie.getZ()))
                    .append(" dist=").append(String.format("%.1f", d))
                    .append(" left_s=").append((ie.lifespan - ie.getAge()) / 20)
                    .append(" in_water=").append(wet);
            n++;
        }
        ok(src, "dshdrop radius=" + String.format("%.0f", radius) + " count=" + found.size()
                + " listed=" + n + " in_water=" + inWater
                + (n == 0 ? " none" : " ::") + sb);
        return n;
    }

    private static int quietProbe(CommandContext<CommandSourceStack> ctx) throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        long now = src.getLevel().getGameTime();
        src.sendSuccess(() -> Component.literal("dshquiet quiet=" + isQuiet(now)
                + " canned=" + CANNED + " humanoid=" + HUMANOID
                + " since_cmd=" + (now - LAST_CMD_TICK) + "t"), false);
        return 1;
    }

    private static int quietCanned(CommandContext<CommandSourceStack> ctx, boolean on)
            throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        CANNED = on;
        src.sendSuccess(() -> Component.literal("dshquiet canned=" + CANNED), false);
        return 1;
    }

    /** ★看见事件 ⇒ 决定要不要"当场反应"★ ✗（说什么 ✓ 以及事件流里留一条 `react` ✓ 让智能体也看得见 ✓） */
    private static void react(String kind, String data) {
        if (!HUMANOID) {
            return;
        }
        ServerPlayer p = botPlayer();
        if (p == null) {
            return;
        }
        ServerLevel lv = lvl(p);
        if (lv == null) {
            return;
        }
        long now = lv.getGameTime();
        if (!isQuiet(now)) {                      // ★智能体在干活 ⇒ 一句话都不说★ ✗
            return;
        }
        if (now - LAST_REACT_TICK < REACT_GAP_TICKS) {
            return;
        }
        if (now - REACT_WINDOW_START > REACT_WINDOW_TICKS) {
            REACT_WINDOW_START = now;
            REACT_COUNT = 0;
        }
        if (REACT_COUNT >= REACT_MAX_PER_WINDOW) {
            return;
        }
        String say = null;
        String why = null;
        switch (kind) {
            case "damage" -> {
                // ★★v2.11.1：按 `src=` 分台词★★ ✗（见上面那组台词表的注释 ✓）
                //   ★读不到 src 就只喊疼★ ✗ —— 绝不默认"有人打我" ✗
                double hp = 20.0;
                String src = "";
                try {
                    int i = data.indexOf("hp=");
                    if (i >= 0) {
                        hp = Double.parseDouble(data.substring(i + 3).split(" ")[0]);
                    }
                    int j = data.indexOf("src=");
                    if (j >= 0) {
                        src = data.substring(j + 4).split(" ")[0];
                    }
                } catch (Exception ignored) {
                    // 解析失败 ⇒ 下面走 PAIN_LINES ✓（只说疼 ✓ 不编来源 ✗）
                }
                if (hp <= 8.0) {
                    say = pick(LOWHP_LINES);
                } else {
                    say = switch (src) {
                        case "drown" -> pick(DROWN_LINES);
                        case "fall", "flyIntoWall" -> pick(FALL_LINES);
                        case "starve" -> pick(STARVE_LINES);
                        case "inFire", "onFire", "lava", "hotFloor" -> pick(BURN_LINES);
                        // ⚠ v2.11.3：**按原版 id 写** ✗（实测教训 ✓）
                        //   我第一次写的是 `mob` / `mobAttack` ✓ 而原版类型 id 是 **`mob_attack`** ✗
                        //   ⇒ 那一击落到了 default ⇒ 只说「疼。」✓（**没编造** ✓ 这是对的 ✓）
                        //     但**本来能说准却被我写成说不准** ✗ ⇒ 别名两种都留着 ✓
                        case "player", "player_attack", "mob", "mob_attack",
                             "arrow", "trident", "thrown", "indirect_magic",
                             "indirectMagic", "mobAttack" -> pick(HURT_LINES);
                        default -> pick(PAIN_LINES);
                    };
                }
                why = "damage hp=" + String.format("%.1f", hp)
                        + " src=" + (src.isEmpty() ? "?" : src);
            }
            case "inv" -> {
                // ★捡到 / 丢了都在这一个事件里★ ✓（`delta=+3` / `delta=-1` ✓）
                int delta = 0;
                try {
                    int i = data.indexOf("delta=");
                    if (i >= 0) {
                        delta = Integer.parseInt(data.substring(i + 6).split(" ")[0].replace("+", ""));
                    }
                } catch (Exception ignored) {
                    return;                        // 读不到就别乱说 ✓
                }
                if (delta > 0) {
                    say = pick(GOT_LINES);
                } else if (delta < 0) {
                    say = pick(LOST_LINES);
                } else {
                    return;                        // 0 件变动 ⇒ 不算事件 ✓ 不开口 ✗
                }
                why = "inv delta=" + delta;
            }
            case "drop_expiring" -> {
                // ★v2.11.1：不许空口承诺 ✗（见 NO_ROOM_LINES 的注释 ✓）
                int free = freeSlots(p);
                say = free > 0 ? pick(EXPIRE_LINES) : pick(NO_ROOM_LINES);
                why = "drop_expiring free=" + free;
            }
            case "mode" -> {
                if (data.contains("WARN_creative")) {
                    say = pick(CREATIVE_LINES);
                    why = "mode_creative";
                }
            }
            case "warp" -> {
                say = pick(WARP_LINES);
                why = "warp";
            }
            case "ate" -> {
                say = pick(ATE_LINES);
                why = "ate";
            }
            case "xp" -> {
                say = pick(XP_LINES);
                why = "xp";
            }
            default -> {
                return;                            // 别的事件不反应 ✓（walk_/idle_/chat 等 ✓）
            }
        }
        if (say == null) {
            return;
        }
        LAST_REACT_TICK = now;
        REACT_COUNT++;
        sayAs(p, say);
        // ★自己在事件流里留一条★ ✗ —— 这样**智能体也能看见"它刚才自己说了什么"** ✓
        //   （不然它那边只看到聊天里多了一句 ✓ 却不知道为什么 ✓）
        String line = "#" + EVENT_SEQ.incrementAndGet() + " react why=" + why
                + " said=" + esc(say) + " n=" + REACT_COUNT
                + (REQ_CTX.get() == null ? "" : " req=" + REQ_CTX.get());
        synchronized (EVENTS) {
            EVENTS.addLast(line);
            while (EVENTS.size() > EVENT_KEEP) {
                EVENTS.removeFirst();
            }
        }
    }

    /** ★把非 ASCII 转义成 `\U+XXXX`★ ✗ —— 中文/表情/任何字符都能**原样带过 CC 通道** ✓
     *  （不转义的话，中文走 CC 命令通道回来会**全变成 `?`** ✗ ⇒ 智能体拿它当判据就静默假阳性 ✗ P13 ✓） */
    private static String esc(String s) {
        if (s == null) {
            return "";
        }
        StringBuilder sb = new StringBuilder(s.length() + 8);
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if (c < 128 && c >= 32) {
                sb.append(c);
            } else {
                sb.append(String.format("\\u%04x", (int) c));
            }
        }
        return sb.toString();
    }

    /** ★把 `U+XXXX` 转义**解回来**★ ✗（`esc()` 的逆 ✓ v2.8.2 ✓）
     *
     * <p>为什么出口也要转义 ✗（2026-09-19 深夜**实测** ✓ 新事实 ✓）：
     * 智能体那边发中文过来 ⇒ 落到游戏聊天里是
     * {@code <Bot> ä½ å¥½ï¼æ¯Botï¼æ£å¨çç¿} ✗ —— 字节是 {@code \xc3\xa4...} ✓
     * ＝ **UTF-8 被当成单字节又编码了一次** ✗（穿过 网关→CC计算机→commands.exec 这条链时坏的 ✗）
     * ⚠ 注意 ✓：模组**自己**发的中文是**好的** ✓（`<Bot> 来了？` ✓ `该收的应该快熟了。` ✓）
     * ⇒ 坏的只是"**从外面送进来的**那一趟" ✗
     * <p>⇒ 修法与事件流**对称** ✓：智能体只发 **纯 ASCII**（非 ASCII 一律写成 `U+XXXX` ✓）
     * 由模组在这里解回真字符 ✓ ⇒ 两趟都不再碰非 ASCII ✓✓
     */
    private static String unesc(String s) {
        if (s == null || s.indexOf("\\u") < 0) {
            return s == null ? "" : s;
        }
        StringBuilder sb = new StringBuilder(s.length());
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if (c == '\\' && i + 5 < s.length() && (s.charAt(i + 1) == 'u' || s.charAt(i + 1) == 'U')) {
                String hex = s.substring(i + 2, i + 6);
                try {
                    sb.append((char) Integer.parseInt(hex, 16));
                    i += 5;
                    continue;
                } catch (NumberFormatException ignored) {
                    // 不是合法转义 ⇒ 原样留着 ✓（别吞字符 ✗）
                }
            }
            sb.append(c);
        }
        return sb.toString();
    }

    /** 以假人的名义说一句话 ✓（形状与聊天一致 ✓ 但它**不是签名聊天** ✗ —— 1.20.1 起签名要客户端 ✓ 见文档 §8.2 ✓） */
    private static void sayAs(ServerPlayer p, String msg) {
        var server = p.getServer();
        if (server == null) {
            return;
        }
        server.getPlayerList().broadcastSystemMessage(
                Component.literal("<" + p.getName().getString() + "> " + msg), false);
    }

    /** ★拟人化的总门槛★ ✗：最近一次模组指令之后**安静够久**了吗 ✓
     *  （干活时每秒都有指令 ✓ ⇒ 它**绝不会**在作业中间自作主张 ✓ 见 P25 ✓） */
    private static boolean isQuiet(long now) {
        return now - LAST_CMD_TICK > HUMANOID_QUIET_TICKS;
    }

    /** 拿能力式物品栏 ✓（拿不到就说人话 ✗ 别装作成功 ✗）
     *
     * <p>★v2.1 加了一层兜底★ ✓：某些方块实体**没有注册** ITEM_HANDLER 能力 ✓
     * 但它其实就是个原版 `Container`（箱子矿车这类 ✓ 以及部分模组方块 ✗）
     * ⇒ 用 Forge 的 `InvWrapper` **包一层** ✓ 于是"是不是容器"这个问题
     * 从"看能力"扩成"**能力 ∪ 原版接口**" ✓（覆盖面一下大了很多 ✓ 而且语义不变 ✓）
     */
    private static IItemHandler handler(CommandSourceStack src, BlockPos pos) {
        BlockEntity be = src.getLevel().getBlockEntity(pos);
        if (be == null) {
            bad(src, "dshbox: " + pos.toShortString() + " is not a block entity (no container here)");
            return null;
        }
        IItemHandler h = be.getCapability(ForgeCapabilities.ITEM_HANDLER, null).orElse(null);
        if (h == null && be instanceof Container c) {
            h = new InvWrapper(c);
        }
        if (h == null) {
            bad(src, "dshbox: " + pos.toShortString() + " has no ITEM_HANDLER capability (not a container)");
            return null;
        }
        return h;
    }

    /** ★实体容器★（箱子矿车 ✓ 漏斗矿车 ✓ 以及一切实现了 Container 的实体 ✓） */
    private static IItemHandler handlerOf(CommandSourceStack src, Entity e) {
        IItemHandler h = e.getCapability(ForgeCapabilities.ITEM_HANDLER, null).orElse(null);
        if (h == null && e instanceof Container c) {
            h = new InvWrapper(c);
        }
        if (h == null) {
            bad(src, "dshbox: " + entityId(e) + " has no item handler (not a container entity)");
            return null;
        }
        return h;
    }

    private static String entityId(Entity e) {
        return String.valueOf(ForgeRegistries.ENTITY_TYPES.getKey(e.getType()));
    }

    /**
     * ★触及距离检查★（真人约束 ✓ 不检查就是能力膨胀 ✗）。
     *
     * <p>实测踩过：假人在 8 格外就能搬桶里的东西 ✓ 当时觉得"真方便"✗
     * —— 但那不是能力 ✓ 是**绕过规则** ✗（见 docs/模组-容器存取与假人手.md §5.4 ✓）
     */
    private static boolean inReach(CommandSourceStack src, ServerPlayer p, BlockPos pos) {
        double d = Math.sqrt(p.distanceToSqr(Vec3.atCenterOf(pos)));
        if (d > REACH) {
            bad(src, String.format("dshbox: too far %.2f > %.1f (walk closer; a real player cannot reach this)",
                    d, REACH));
            return false;
        }
        return true;
    }

    // ══════════════════════════════════════════════════════════════════════════
    // /dshbox —— 容器
    // ══════════════════════════════════════════════════════════════════════════

    private static final int PAGE = 24;   // 每页显示多少格（大容器 132 格看不全 ✗ ⇒ v2.1 分页 ✓）

    private static int peek(CommandContext<CommandSourceStack> ctx, int page) throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        BlockPos pos = BlockPosArgument.getLoadedBlockPos(ctx, "pos");
        IItemHandler h = handler(src, pos);
        if (h == null) {
            return 0;
        }
        // ⚠ 只读也做触及检查 ✗（不然"眼睛"能看穿半个世界 ✗ 与真人差太远 ✗）
        ServerPlayer p = src.getPlayer();
        if (p != null && !inReach(src, p, pos)) {
            return 0;
        }
        return peekHandler(src, h, "dshbox peek " + pos.toShortString(), page);
    }

    /** ★v2.1 抽出来的公共实现★ ⇒ 方块容器 ✓ 与**实体容器** ✓ 共用一套分页输出 ✓ */
    private static int peekHandler(CommandSourceStack src, IItemHandler h, String head, int page) {
        int kinds = 0, total = 0;
        List<String> entries = new ArrayList<>();
        for (int i = 0; i < h.getSlots(); i++) {
            ItemStack s = h.getStackInSlot(i);
            if (s.isEmpty()) {
                continue;
            }
            kinds++;
            total += s.getCount();
            entries.add("[" + i + "]" + idOf(s) + "x" + s.getCount());
        }
        int pages = Math.max(1, (entries.size() + PAGE - 1) / PAGE);
        int pg = Math.max(1, Math.min(page, pages));
        int from = (pg - 1) * PAGE;
        int to = Math.min(from + PAGE, entries.size());
        StringBuilder sb = new StringBuilder(head + " slots=" + h.getSlots() + " items=" + total
                + " kinds=" + kinds + " page=" + pg + "/" + pages);
        for (int i = from; i < to; i++) {
            sb.append(" ").append(entries.get(i));
        }
        ok(src, sb.toString());
        return kinds;
    }

    private static int take(CommandContext<CommandSourceStack> ctx, String filter, int want)
            throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        BlockPos pos = BlockPosArgument.getLoadedBlockPos(ctx, "pos");
        IItemHandler h = handler(src, pos);
        if (h == null) {
            return 0;
        }
        ServerPlayer p = src.getPlayerOrException();
        if (!inReach(src, p, pos)) {
            return 0;
        }
        int moved = 0, kinds = 0;
        for (int i = 0; i < h.getSlots() && moved < want; i++) {
            ItemStack inSlot = h.getStackInSlot(i);
            if (inSlot.isEmpty()) {
                continue;
            }
            if (!filter.isEmpty() && !idOf(inSlot).contains(filter)) {
                continue;
            }
            int n = Math.min(want - moved, inSlot.getCount());
            // ★ 先真取出来 ✓ 再往背包塞 ✓ 塞不下的**原样放回** ✗（绝不静默吞 ✗）
            ItemStack taken = h.extractItem(i, n, false);
            if (taken.isEmpty()) {
                continue;
            }
            int got = taken.getCount();
            p.getInventory().add(taken);
            if (!taken.isEmpty()) {                       // 背包满了 ⇒ 余量放回原槽 ✓
                ItemStack back = h.insertItem(i, taken, false);
                if (!back.isEmpty()) {
                    p.drop(back, false);                  // 连放回都失败 ⇒ 掉脚下 ✓ 也不让它消失 ✗
                }
                bad(src, "dshbox: inventory full; returned " + back.getCount()
                        + " (moved " + (got - back.getCount()) + ")");
            }
            moved += got - taken.getCount();
            kinds++;
        }
        ok(src, "dshbox take " + pos.toShortString() + " moved kinds=" + kinds + " items=" + moved);
        return moved;
    }

    private static int put(CommandContext<CommandSourceStack> ctx, String filter, int want)
            throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        BlockPos pos = BlockPosArgument.getLoadedBlockPos(ctx, "pos");
        IItemHandler h = handler(src, pos);
        if (h == null) {
            return 0;
        }
        ServerPlayer p = src.getPlayerOrException();
        if (!inReach(src, p, pos)) {
            return 0;
        }
        int moved = 0, kinds = 0;
        for (int slot = 0; slot < p.getInventory().getContainerSize() && moved < want; slot++) {
            ItemStack s = p.getInventory().getItem(slot);
            if (s.isEmpty()) {
                continue;
            }
            if (!filter.isEmpty() && !idOf(s).contains(filter)) {
                continue;
            }
            int n = Math.min(want - moved, s.getCount());
            ItemStack left = s.copyWithCount(n);
            for (int i = 0; i < h.getSlots() && !left.isEmpty(); i++) {
                left = h.insertItem(i, left, false);
            }
            int putN = n - left.getCount();
            if (putN > 0) {
                s.shrink(putN);
                moved += putN;
                kinds++;
            }
            if (!left.isEmpty()) {                        // 容器满 ⇒ 放得下多少算多少 ✓ 如实报 ✗
                bad(src, "dshbox: container full; " + left.getCount() + " left in inventory");
                break;
            }
        }
        ok(src, "dshbox put " + pos.toShortString() + " moved kinds=" + kinds + " items=" + moved);
        return moved;
    }

    // ══════════════════════════════════════════════════════════════════════════
    // /dshuse —— 对着方块的指定面右键（★补"没有客户端"最核心的那一环★）
    // ══════════════════════════════════════════════════════════════════════════

    private static Direction parseFace(String s) {
        switch (s == null ? "" : s.toLowerCase()) {
            case "up":    return Direction.UP;
            case "down":  return Direction.DOWN;
            case "north": return Direction.NORTH;
            case "south": return Direction.SOUTH;
            case "east":  return Direction.EAST;
            case "west":  return Direction.WEST;
            default:      return null;
        }
    }

    private static int useOn(CommandContext<CommandSourceStack> ctx, float aimY)
            throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        BlockPos pos = BlockPosArgument.getLoadedBlockPos(ctx, "pos");
        Direction face = parseFace(StringArgumentType.getString(ctx, "face"));
        if (face == null) {
            bad(src, "dshuse: face must be up/down/north/south/east/west");
            return 0;
        }
        ServerPlayer p = src.getPlayerOrException();
        ServerLevel level = (ServerLevel) src.getLevel();

        double d = Math.sqrt(p.distanceToSqr(Vec3.atCenterOf(pos)));
        if (d > REACH) {
            bad(src, String.format("dshuse: too far %.2f > %.1f", d, REACH));
            return 0;
        }

        // 命中点 = 这一面中心 ✓ 但 y 可以按 aimY 调整 ✓
        // ★ aimY 是给"碗形方块"（筛子 ✗）准备的：必须从上方射进碗里（命中面 up）★
        Vec3 c = Vec3.atCenterOf(pos);
        double hx = c.x + face.getStepX() * 0.5;
        double hy = c.y + face.getStepY() * 0.5;
        double hz = c.z + face.getStepZ() * 0.5;
        if (face.getStepY() == 0) {                       // 平面朝向的四个面 ⇒ 调高度 ✓
            hy = pos.getY() + aimY;
        } else if (face == Direction.UP) {                // 顶面 ⇒ 调平面内的落点 ✓
            hx = pos.getX() + 0.5;
            hz = pos.getZ() + 0.5;
            hy = pos.getY() + 1.0 - (1.0 - aimY) * 0.2;   // aimY 小 ⇒ 略微"进碗" ✓
        }
        Vec3 hitVec = new Vec3(hx, hy, hz);

        String before = blockName(level, pos);
        ItemStack held = p.getItemInHand(InteractionHand.MAIN_HAND);
        String heldBefore = held.isEmpty() ? "empty" : idOf(held) + "x" + held.getCount();

        // ★ 把假人的朝向也对准这个命中点 ✓
        //   为什么必须做 ✗：`crosshair`（准星感知）读的就是 Pos+Rotation ✓
        //   若朝向与实际命中点不一致 ⇒ 智能体会"看到"一个它其实没打的方向 ✗
        aimAt(p, hitVec);

        // ★ 走**真人那条服务端路径** ✓：
        //   `ServerPlayerGameMode.useItemOn` 就是客户端发 ServerboundUseItemOnPacket 之后
        //   服务端跑的那一句 ✓ ⇒ 它会照常触发 ForgeHooks.onRightClickBlock ✓
        //   ⇒ KubeJS 的 `BlockEvents.rightClicked` 之类**一样会响** ✓✓
        BlockHitResult bhr = new BlockHitResult(hitVec, face, pos, false);
        InteractionResult ir;
        try {
            ir = p.gameMode.useItemOn(p, level, held, InteractionHand.MAIN_HAND, bhr);
        } catch (Exception e) {
            bad(src, "dshuse: server threw while using: " + e.getClass().getSimpleName() + " " + e.getMessage());
            return 0;
        }
        p.swing(InteractionHand.MAIN_HAND, true);

        String after = blockName(level, pos);
        ItemStack heldNow = p.getItemInHand(InteractionHand.MAIN_HAND);
        String heldAfter = heldNow.isEmpty() ? "empty" : idOf(heldNow) + "x" + heldNow.getCount();

        ok(src, String.format("dshuse %s face=%s result=%s block %s -> %s held %s -> %s",
                pos.toShortString(), face.getName(), ir, before, after, heldBefore, heldAfter));
        evMut(pos, before, after);         // ★★§79.412✗★ 开门/互动改了方块也要说✗★
        return ir == InteractionResult.FAIL ? 0 : 1;
    }

    private static void aimAt(ServerPlayer p, Vec3 target) {
        Vec3 eye = p.getEyePosition();
        double dx = target.x - eye.x, dy = target.y - eye.y, dz = target.z - eye.z;
        double horiz = Math.sqrt(dx * dx + dz * dz);
        float yaw = (float) (Math.toDegrees(Math.atan2(-dx, dz)));
        float pitch = (float) (Math.toDegrees(-Math.atan2(dy, horiz)));
        p.setYRot(yaw);
        p.setXRot(pitch);
        p.setYHeadRot(yaw);
    }

    private static String blockName(ServerLevel level, BlockPos pos) {
        return ForgeRegistries.BLOCKS.getKey(level.getBlockState(pos).getBlock()).toString();
    }

    // ══════════════════════════════════════════════════════════════════════════
    // /dshcraft —— 工作台合成（不开界面 ✓ 数据驱动 ✓ 通吃模组配方 ✓）
    // ══════════════════════════════════════════════════════════════════════════

    /** 找配方：先当 recipe id ✓ 再按"产物物品"匹配 ✓ 只收 3×3 做得出来的 ✓ */
    private static Recipe<?> findRecipe(ServerLevel level, String want) {
        var rm = level.getRecipeManager();
        // ① 先当 **recipe id** 找 ✓（`/dshcraft recipes <item>` 会把 id 告诉你 ✓）
        if (want.contains(":")) {
            Optional<? extends Recipe<?>> byId = rm.byKey(new ResourceLocation(want));
            if (byId.isPresent() && usable(byId.get())) {
                return byId.get();
            }
        }
        // ② 再按**产物物品**找 ✓（第一个能用的 ✓）
        String id = want.contains(":") ? want : "minecraft:" + want;
        for (Recipe<?> r : rm.getAllRecipesFor(RecipeType.CRAFTING)) {
            if (!usable(r)) {
                continue;
            }
            ItemStack out = r.getResultItem(level.registryAccess());
            if (!out.isEmpty() && idOf(out).equals(id)) {
                return r;
            }
        }
        return null;
    }

    /**
     * ★只收"真人在 3×3 工作台上做得出来"的配方★ ✗
     * <p>为什么写死这一条 ✗：服务端配方表里还有 2×2 背包配方 ✓ 3×3 工作台配方 ✓
     * 以及**各种机器配方**（熔炼 ✓ 粉碎 ✓ 注液 ✓…）✗ —— 后者需要对应的机器 ✓
     * 若不加限制，"合成"就会变成**凭空造物** ✗（那就不是像真人 ✓ 而是作弊 ✗）
     */
    private static boolean usable(Recipe<?> r) {
        if (!(r instanceof CraftingRecipe cr)) {
            return false;
        }
        if (r.getType() != RecipeType.CRAFTING) {
            return false;
        }
        try {
            return cr.canCraftInDimensions(3, 3);
        } catch (Throwable t) {
            return false;
        }
    }

    /** 干跑一遍：够不够料 ✓ 放不放得下 ✓（**先确认再动手** ✗ 见纪律 2 ✓） */
    private static String[] dryRun(ServerPlayer p, Recipe<?> r, int times) {
        List<Ingredient> ings = new ArrayList<>(r.getIngredients());
        ings.removeIf(Ingredient::isEmpty);
        int size = p.getInventory().getContainerSize();
        int[] avail = new int[size];
        for (int i = 0; i < size; i++) {
            ItemStack s = p.getInventory().getItem(i);
            avail[i] = s.isEmpty() ? 0 : s.getCount();
        }
        for (int t = 0; t < times; t++) {
            for (Ingredient ing : ings) {
                boolean got = false;
                for (int i = 0; i < size && !got; i++) {
                    if (avail[i] <= 0) {
                        continue;
                    }
                    ItemStack s = p.getInventory().getItem(i);
                    if (!s.isEmpty() && ing.test(s)) {
                        avail[i]--;
                        got = true;
                    }
                }
                if (!got) {
                    StringBuilder need = new StringBuilder();
                    for (Ingredient x : ings) {
                        ItemStack[] m = x.getItems();
                        need.append(need.length() == 0 ? "" : " + ")
                            .append(m.length > 0 ? idOf(m[0]) : "?");
                    }
                    return new String[]{"no_materials", need.toString()};
                }
            }
        }
        ItemStack out = r.getResultItem(p.level().registryAccess());
        if (!hasRoom(p, out.copyWithCount(out.getCount() * times))) {
            return new String[]{"no_room", idOf(out)};
        }
        return null;
    }

    /** 放得下吗 ✗（**这是"静默吞物品"事故的根因** ✓ 见 KubeJS 版的账 ✓） */
    private static boolean hasRoom(ServerPlayer p, ItemStack out) {
        int need = out.getCount();
        for (int i = 0; i < p.getInventory().getContainerSize(); i++) {
            ItemStack s = p.getInventory().getItem(i);
            if (s.isEmpty()) {
                need -= Math.min(need, out.getMaxStackSize());
            } else if (ItemStack.isSameItemSameTags(s, out)) {
                need -= Math.min(need, s.getMaxStackSize() - s.getCount());
            }
            if (need <= 0) {
                return true;
            }
        }
        return need <= 0;
    }

    private static int craftCan(CommandContext<CommandSourceStack> ctx, int times) throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        ServerPlayer p = src.getPlayerOrException();
        Recipe<?> r = findRecipe((ServerLevel) src.getLevel(),
                StringArgumentType.getString(ctx, "item"));
        if (r == null) {
            ok(src, "dshcraft can " + StringArgumentType.getString(ctx, "item") + " ok=false reason=no_recipe");
            return 0;
        }
        String[] why = dryRun(p, r, times);
        ItemStack out = r.getResultItem(src.getLevel().registryAccess());
        ok(src, String.format("dshcraft can %s times=%d ok=%s out=%s x%d reason=%s",
                StringArgumentType.getString(ctx, "item"), times, why == null, idOf(out),
                out.getCount() * times, why == null ? "none" : why[0]));
        return why == null ? 1 : 0;
    }

    private static int craftRecipes(CommandContext<CommandSourceStack> ctx) throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        String want = StringArgumentType.getString(ctx, "item");
        String id = want.contains(":") ? want : "minecraft:" + want;
        StringBuilder sb = new StringBuilder("dshcraft recipes " + id + " =>");
        int n = 0;
        for (Recipe<?> r : ((ServerLevel) src.getLevel()).getRecipeManager().getAllRecipesFor(RecipeType.CRAFTING)) {
            if (!usable(r)) {
                continue;
            }
            ItemStack out = r.getResultItem(src.getLevel().registryAccess());
            if (!out.isEmpty() && idOf(out).equals(id) && n < 6) {
                sb.append(" [").append(r.getId()).append(" x").append(out.getCount()).append("]");
                n++;
            }
        }
        ok(src, n == 0 ? sb.append(" (none)").toString() : sb.toString());
        return n;
    }

    private static int craft(CommandContext<CommandSourceStack> ctx, int times) throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        ServerPlayer p = src.getPlayerOrException();
        String want = StringArgumentType.getString(ctx, "item");
        Recipe<?> r = findRecipe((ServerLevel) src.getLevel(), want);
        if (r == null) {
            bad(src, "dshcraft: no craftable (3x3) recipe for '" + want + "' - try /dshcraft recipes " + want);
            return 0;
        }
        String[] why = dryRun(p, r, times);
        if (why != null) {
            if ("no_room".equals(why[0])) {
                bad(src, "dshcraft: no room in inventory for " + why[1] + " - nothing was consumed");
            } else {
                bad(src, "dshcraft: not enough materials, need " + why[1] + " - nothing was consumed");
            }
            return 0;
        }
        List<Ingredient> ings = new ArrayList<>(r.getIngredients());
        ings.removeIf(Ingredient::isEmpty);
        int done = 0;
        for (int t = 0; t < times; t++) {
            for (Ingredient ing : ings) {
                for (int i = 0; i < p.getInventory().getContainerSize(); i++) {
                    ItemStack s = p.getInventory().getItem(i);
                    if (!s.isEmpty() && ing.test(s)) {
                        s.shrink(1);
                        break;
                    }
                }
            }
            ItemStack out = r.getResultItem(p.level().registryAccess()).copy();
            p.getInventory().add(out);
            if (!out.isEmpty()) {                          // 放不下 ⇒ 不许悄悄消失 ✗
                p.drop(out, false);
                bad(src, "dshcraft: inventory full mid-way; dropped " + out.getCount() + " on the ground");
                break;
            }
            done++;
        }
        ItemStack res = r.getResultItem(p.level().registryAccess());
        ok(src, String.format("dshcraft %s done=%d out=%s x%d now_have=%d",
                want, done, idOf(res), res.getCount() * done, countOf(p, idOf(res))));
        return done;
    }

    private static int countOf(ServerPlayer p, String id) {
        int n = 0;
        for (int i = 0; i < p.getInventory().getContainerSize(); i++) {
            ItemStack s = p.getInventory().getItem(i);
            if (!s.isEmpty() && idOf(s).equals(id)) {
                n += s.getCount();
            }
        }
        return n;
    }

    // ══════════════════════════════════════════════════════════════════════════
    // /dshslot —— 按槽位精确读写（v2.1 ✓）
    // ══════════════════════════════════════════════════════════════════════════

    private static int slotGet(CommandContext<CommandSourceStack> ctx) throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        BlockPos pos = BlockPosArgument.getLoadedBlockPos(ctx, "pos");
        IItemHandler h = handler(src, pos);
        if (h == null) {
            return 0;
        }
        ServerPlayer p = src.getPlayer();
        if (p != null && !inReach(src, p, pos)) {
            return 0;
        }
        int slot = IntegerArgumentType.getInteger(ctx, "slot");
        if (slot >= h.getSlots()) {
            bad(src, "dshslot: slot " + slot + " out of range (0.." + (h.getSlots() - 1) + ")");
            return 0;
        }
        ItemStack s = h.getStackInSlot(slot);
        ok(src, "dshslot get " + pos.toShortString() + " slot=" + slot + " "
                + (s.isEmpty() ? "empty" : idOf(s) + "x" + s.getCount()));
        return s.isEmpty() ? 0 : s.getCount();
    }

    private static int slotTake(CommandContext<CommandSourceStack> ctx, int count) throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        BlockPos pos = BlockPosArgument.getLoadedBlockPos(ctx, "pos");
        IItemHandler h = handler(src, pos);
        if (h == null) {
            return 0;
        }
        ServerPlayer p = src.getPlayerOrException();
        if (!inReach(src, p, pos)) {
            return 0;
        }
        int slot = IntegerArgumentType.getInteger(ctx, "slot");
        if (slot >= h.getSlots()) {
            bad(src, "dshslot: slot " + slot + " out of range (0.." + (h.getSlots() - 1) + ")");
            return 0;
        }
        // ★ 先真取出来 ✓ 再往背包塞 ✓ 塞不下的**原样放回** ✗（绝不静默吞 ✗ 纪律 2 ✓）
        ItemStack taken = h.extractItem(slot, count, false);
        if (taken.isEmpty()) {
            bad(src, "dshslot: slot " + slot + " is empty");
            return 0;
        }
        int got = taken.getCount();
        p.getInventory().add(taken);
        if (!taken.isEmpty()) {
            ItemStack back = h.insertItem(slot, taken, false);
            if (!back.isEmpty()) {
                p.drop(back, false);
            }
            bad(src, "dshslot: inventory full; returned " + back.getCount()
                    + " (moved " + (got - back.getCount()) + ")");
        }
        ok(src, "dshslot take " + pos.toShortString() + " slot=" + slot + " moved=" + (got - taken.getCount()));
        return got - taken.getCount();
    }

    private static int slotPut(CommandContext<CommandSourceStack> ctx, int count) throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        BlockPos pos = BlockPosArgument.getLoadedBlockPos(ctx, "pos");
        IItemHandler h = handler(src, pos);
        if (h == null) {
            return 0;
        }
        ServerPlayer p = src.getPlayerOrException();
        if (!inReach(src, p, pos)) {
            return 0;
        }
        int slot = IntegerArgumentType.getInteger(ctx, "slot");
        if (slot >= h.getSlots()) {
            bad(src, "dshslot: slot " + slot + " out of range (0.." + (h.getSlots() - 1) + ")");
            return 0;
        }
        ItemStack held = p.getMainHandItem();
        if (held.isEmpty()) {
            bad(src, "dshslot: main hand is empty - hold the item first (use dshinv hotbar/equip)");
            return 0;
        }
        String id = idOf(held);
        int n = Math.min(count, held.getCount());
        // ⚠ `insertItem` 可能**只收一部分**（槽位有上限 ✓ 或它是个被过滤的槽 ✗）
        //   ⇒ 只有它真收下的才算数 ✓ 余量留在手里 ✓（绝不"扣了却没进去"✗）
        ItemStack left = h.insertItem(slot, held.copyWithCount(n), false);
        int putN = n - left.getCount();
        if (putN <= 0) {
            bad(src, "dshslot: slot " + slot + " rejected the item (full or filtered)");
            return 0;
        }
        held.shrink(putN);
        ok(src, "dshslot put " + pos.toShortString() + " slot=" + slot + " " + id + "x" + putN + " ok");
        return putN;
    }

    // ══════════════════════════════════════════════════════════════════════════
    // /dshentbox —— 实体容器（箱子矿车 ✓ 漏斗矿车 ✓ v2.1 ✓）
    // ══════════════════════════════════════════════════════════════════════════

    private static int entBoxPeek(CommandContext<CommandSourceStack> ctx, int page) throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        ServerPlayer p = src.getPlayerOrException();
        Entity e = EntityArgument.getEntity(ctx, "target");
        if (p.distanceTo(e) > REACH) {
            bad(src, String.format("dshentbox: too far %.2f > %.1f", p.distanceTo(e), REACH));
            return 0;
        }
        IItemHandler h = handlerOf(src, e);
        if (h == null) {
            return 0;
        }
        return peekHandler(src, h, "dshentbox peek " + entityId(e), page);
    }

    private static int entBoxTake(CommandContext<CommandSourceStack> ctx, String filter, int want)
            throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        ServerPlayer p = src.getPlayerOrException();
        Entity e = EntityArgument.getEntity(ctx, "target");
        if (p.distanceTo(e) > REACH) {
            bad(src, String.format("dshentbox: too far %.2f > %.1f", p.distanceTo(e), REACH));
            return 0;
        }
        IItemHandler h = handlerOf(src, e);
        if (h == null) {
            return 0;
        }
        int moved = 0, kinds = 0;
        for (int i = 0; i < h.getSlots() && moved < want; i++) {
            ItemStack inSlot = h.getStackInSlot(i);
            if (inSlot.isEmpty() || (!filter.isEmpty() && !idOf(inSlot).contains(filter))) {
                continue;
            }
            int n = Math.min(want - moved, inSlot.getCount());
            ItemStack taken = h.extractItem(i, n, false);
            if (taken.isEmpty()) {
                continue;
            }
            int got = taken.getCount();
            p.getInventory().add(taken);
            if (!taken.isEmpty()) {
                ItemStack back = h.insertItem(i, taken, false);
                if (!back.isEmpty()) {
                    p.drop(back, false);
                }
                bad(src, "dshentbox: inventory full; returned " + back.getCount()
                        + " (moved " + (got - back.getCount()) + ")");
            }
            moved += got - taken.getCount();
            kinds++;
        }
        ok(src, "dshentbox take " + entityId(e) + " moved kinds=" + kinds + " items=" + moved);
        return moved;
    }

    private static int entBoxPut(CommandContext<CommandSourceStack> ctx, String filter, int want)
            throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        ServerPlayer p = src.getPlayerOrException();
        Entity e = EntityArgument.getEntity(ctx, "target");
        if (p.distanceTo(e) > REACH) {
            bad(src, String.format("dshentbox: too far %.2f > %.1f", p.distanceTo(e), REACH));
            return 0;
        }
        IItemHandler h = handlerOf(src, e);
        if (h == null) {
            return 0;
        }
        int moved = 0, kinds = 0;
        for (int slot = 0; slot < p.getInventory().getContainerSize() && moved < want; slot++) {
            ItemStack s = p.getInventory().getItem(slot);
            if (s.isEmpty() || (!filter.isEmpty() && !idOf(s).contains(filter))) {
                continue;
            }
            int n = Math.min(want - moved, s.getCount());
            ItemStack left = s.copyWithCount(n);
            for (int i = 0; i < h.getSlots() && !left.isEmpty(); i++) {
                left = h.insertItem(i, left, false);
            }
            int putN = n - left.getCount();
            if (putN > 0) {
                s.shrink(putN);
                moved += putN;
                kinds++;
            }
            if (!left.isEmpty()) {
                bad(src, "dshentbox: container full; " + left.getCount() + " left in inventory");
                break;
            }
        }
        ok(src, "dshentbox put " + entityId(e) + " moved kinds=" + kinds + " items=" + moved);
        return moved;
    }

    // ══════════════════════════════════════════════════════════════════════════
    // /dshtrade —— 跟村民交易（走原版那条路 ✓ 与服务端处理选交易包时同一套调用 ✓）
    // ══════════════════════════════════════════════════════════════════════════

    /** 打开商人菜单 ✓（打不开就**说清为什么** ✗：太远 ✓ / 不是村民 ✓ / 没职业 ✓） */
    private static net.minecraft.world.inventory.MerchantMenu openMerchant(
            CommandSourceStack src, ServerPlayer p, Entity target) {
        if (!(target instanceof net.minecraft.world.entity.npc.AbstractVillager v)) {
            bad(src, "dshtrade: " + entityId(target) + " is not a villager");
            return null;
        }
        double dd = p.distanceTo(v);
        if (dd > REACH) {
            bad(src, String.format("dshtrade: too far %.2f > %.1f", dd, REACH));
            return null;
        }
        aimAt(p, v.position().add(0, v.getBbHeight() * 0.5, 0));
        p.interactOn(v, InteractionHand.MAIN_HAND);
        if (!(p.containerMenu instanceof net.minecraft.world.inventory.MerchantMenu mm)) {
            bad(src, "dshtrade: no merchant menu opened (villager has no profession or no offers)");
            return null;
        }
        return mm;
    }

    private static int tradeList(CommandContext<CommandSourceStack> ctx) throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        ServerPlayer p = src.getPlayerOrException();
        Entity e = EntityArgument.getEntity(ctx, "target");
        var mm = openMerchant(src, p, e);
        if (mm == null) {
            return 0;
        }
        var offers = mm.getOffers();
        StringBuilder sb = new StringBuilder("dshtrade list " + entityId(e) + " offers=" + offers.size());
        for (int i = 0; i < Math.min(offers.size(), 8); i++) {
            var o = offers.get(i);
            sb.append(" [").append(i).append("]").append(idOf(o.getBaseCostA())).append("x").append(o.getBaseCostA().getCount());
            // ⚠ 1.20.1 里第二个材料叫 `getCostB()` ✗ —— 没有 `getBaseCostB()` ✗
            //   （`getBaseCostA()` 有 ✓ 一对里只有 A 带 Base ✓ 这种不对称只能问编译器 ✓）
            if (!o.getCostB().isEmpty()) {
                sb.append("+").append(idOf(o.getCostB())).append("x").append(o.getCostB().getCount());
            }
            sb.append("->").append(idOf(o.getResult())).append("x").append(o.getResult().getCount())
              .append("(").append(o.getUses()).append("/").append(o.getMaxUses()).append(")");
        }
        ok(src, sb.toString());
        p.closeContainer();
        return offers.size();
    }

    // ── v2.5 新增的两个小工具（都在修 P20 那三个真问题 ✓）──────────────────────
    /**
     * ★背包下标 → 菜单槽号★ ✗
     *
     * <p>为什么必须这么写 ✗（v2.4 的 bug 就在这里 ✓ 见错题本 P20 ✓）：
     * v2.4 直接写了 `mm.clicked(3 + free, …)` ✗ —— 可 `free` 是**背包下标**(0..35) ✓
     * 而商人菜单的布局是 ✗：
     * <pre>
     *   menu 0,1   = 付款槽          menu 2      = 结果槽
     *   menu 3..29 = 背包 9..35（主区 27 格）    menu 30..38 = 背包 0..8（快捷栏 9 格）
     * </pre>
     * ⇒ `3 + free` 只有当 `free` 落在 9..35 时才**碰巧**对 ✓
     * 落在 0..8（快捷栏）时会**打到主区的另一格** ✗ ⇒ 那一格若已有东西 ⇒ 变成**交换** ✗
     * ⇒ 产物不并堆 ✗ 手里(光标)还留着换出来的东西 ✗（后面那一笔就废了 ✗ 关菜单时东西掉地上 ✗）
     *
     * <p>★做法上更稳的一步★ ✓：**不手算** ✓ 而是按"容器与容器槽位"去菜单里**找** ✓
     * —— 这样即使以后菜单布局变了也不怕 ✓（手算的公式是"猜"✗ 查表是"事实"✓）
     *
     * @return 菜单槽号；找不到返回 -1 ✓（调用方必须**如实报错**✗ 不许硬着头皮点 ✗）
     */
    private static int menuSlotOf(net.minecraft.world.inventory.AbstractContainerMenu mm,
                                  net.minecraft.world.entity.player.Player p, int invIndex) {
        for (int i = 0; i < mm.slots.size(); i++) {
            var s = mm.slots.get(i);
            if (s.container == p.getInventory() && s.getContainerSlot() == invIndex) {
                return i;
            }
        }
        return -1;
    }

    /** 找一个空的背包槽（0..35 ✓ 不含护甲/副手 ✗）→ 没有返回 -1 ✓ */
    private static int findFreeSlot(ServerPlayer p) {
        for (int k = 0; k < 36; k++) {
            if (p.getInventory().getItem(k).isEmpty()) {
                return k;
            }
        }
        return -1;
    }

    /**
     * ★★把付款槽里剩下的钱**放回背包**★★ ✗
     *
     * <p>为什么非做不可 ✗（这是 P20 里**最贵**的那一条 ✓）：
     * `tryMoveItems` 会把**整堆**材料塞进付款槽（实测：28 个绿宝石 ✗）
     * 而一笔只花掉 4 个 ⇒ **余额**若不显式放回去 ✗ 关菜单时就会**掉在世界里** ✗
     * 实测后果 ✓：25 个绿宝石躺在地上 ✗ 而当时背包**正好满** ✗ ⇒ **捡不起来** ✗ ⇒ 5 分钟消失 ✗✗
     *
     * <p>纪律 ✓（错题本 P19.1 / 纪律⑤ ✓）：**绝不静默丢物品** ✗
     * ⇒ 放得下就放回 ✓ 放不下就**留在付款槽里并大声报** ✗（宁可让它停在这儿等下一次 ✓ 也不许丢 ✗）
     *
     * @return 实际放回背包的件数 ✓
     */
    /** 把付款槽里剩下的钱**放回背包** ✗（v2.5 ✓ 保留 ✓ —— 精确装料之后它多半无事可做 ✓
     *  但**留着**是有意的 ✓：万一装料那条路退回原版 ✗ 余款还是得有人管 ✓） */
    private static int refundPayment(CommandSourceStack src, ServerPlayer p,
                                     net.minecraft.world.inventory.MerchantMenu mm) {
        int returned = 0;
        int stuck = 0;
        for (int s = 0; s < 2; s++) {
            var slot = mm.getSlot(s);
            ItemStack rest = slot.getItem();
            if (rest.isEmpty()) {
                continue;
            }
            ItemStack copy = rest.copy();
            slot.set(ItemStack.EMPTY);                 // 先从付款槽拿出来 ✓
            if (p.getInventory().add(copy)) {
                returned += copy.getCount();
            } else {
                slot.set(copy);                        // 放不下 ⇒ **原样退回**（不是丢掉 ✗）
                stuck += copy.getCount();
            }
        }
        mm.broadcastChanges();
        if (stuck > 0) {
            bad(src, "dshtrade: refund could not fit in inventory - " + stuck
                     + " item(s) left in the payment slot (NOT dropped)");
        }
        return returned;
    }

    /** 把含 `want` 的那一堆**换到手上** ✓ → 成功返回 true ✓
     *
     * <p>★为什么模组里要自己写一个★ ✗（实测栽了两次 ✓）：
     * Lua 那侧的 `hold_item` **只翻快捷栏（0..8）** ✗ 而物品常常躺在主背包（9..35）✗
     * ⇒ 回执是"快捷栏里没有含 X 的物品"✗ —— 看着像"根本没这东西"✗ 其实是"没拿在手上"✗
     * ⇒ 然后上层就会以为"工具丢了/没做出来"✗（diorite ✓ 木锤 ✓ 各骗了我一次 ✓）
     *
     * <p>做法与真人一致 ✓：找到那一堆 ⇒ **与当前选中的快捷栏槽交换** ✓（不需要有空槽 ✓）
     */
    private static boolean ensureHeld(ServerPlayer p, String want) {
        var inv = p.getInventory();
        int sel = inv.selected;
        for (int i = 0; i < 36; i++) {
            ItemStack s = inv.getItem(i);
            if (!s.isEmpty() && idOf(s).contains(want)) {
                if (i == sel) {
                    return true;
                }
                ItemStack a = inv.getItem(sel).copy();
                ItemStack b = s.copy();
                inv.setItem(sel, b);
                inv.setItem(i, a);
                inv.selected = sel;
                return true;
            }
        }
        return false;
    }

    /** `/dshequip <item>` —— ★把任意物品**换到手上**★ ✓（含主背包 0..35 ✓）
     *
     * <p>为什么单拎出来一条 ✗（实测栽了**三次** ✓ 见错题本 **P29** ✓）：
     * Lua 那侧 `hold_item` **只翻快捷栏** ✗ ⇒ "手不对"时现场表现五花八门 ✗：
     * ① diorite 放不上去 ✗ ② 木锤砸不动方块 ✗ ③ 反过来 `dshplace` 为了拿料**把锤子挤出手中** ✗
     * ⇒ 三件事看起来毫不相干 ✗ 其实是**同一个坑** ✓
     * ⇒ 所以给 agent 一条**能按名字拿东西**的指令 ✓（能不能拿到**如实回**✗ 不假装 ✓）
     */
    private static int equip(CommandContext<CommandSourceStack> ctx) throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        ServerPlayer p = src.getPlayerOrException();
        String item = StringArgumentType.getString(ctx, "item");
        if (!ensureHeld(p, item)) {
            bad(src, "dshequip: " + item + " not found in inventory (0..35) - hand unchanged");
            return 0;
        }
        ItemStack held = p.getMainHandItem();
        boolean okk = !held.isEmpty() && idOf(held).contains(item);
        if (okk) {
            ok(src, "dshequip " + item + " held=" + idOf(held) + "x" + held.getCount()
                    + " slot=" + p.getInventory().selected + " verified=true");
            return 1;
        }
        bad(src, "dshequip: hand ended up as " + (held.isEmpty() ? "empty" : idOf(held))
                + " (wanted " + item + ")");
        return 0;
    }

    // ── /dshplace ─────────────────────────────────────────────────────────────
    /**
     * ★显式放方块 ＋ **落点校验**★ ✗（v2.7 ✓）
     *
     * <p>为什么需要它 ✗（实测现场 ✓ 见错题本 **P30** ✓）：
     * 用 `/dshuse <地基> up` 放方块时 ✓ 同一条指令**一次 `FAIL`、一次 `CONSUME`** ✗
     * 而 `FAIL` **什么原因都不说** ✗ ⇒ 上层只能猜（"是不是够不着？是不是手不对？"）✗
     *
     * <p>这条把整件事变成**可判读**的 ✓：
     * <ol>
     *   <li>先把物品**换到手上** ✓（`ensureHeld` ✓ 找不到就**明说**✗）</li>
     *   <li>目标格必须**是空气** ✓（不然直接说"那格已经有东西"✗）</li>
     *   <li>在六邻格里找一个**能站人的支撑面** ✓（朝向玩家的那一面优先 ✓）</li>
     *   <li>调**真人那条** `useItemOn` ✓</li>
     *   <li>★**读世界真值复核**★ ✗：目标格现在是不是那个方块 ✓ —— 不以 `useItemOn` 的返回值为准 ✗</li>
     * </ol>
     */
    // ── /dshdig ───────────────────────────────────────────────────────────────
    //   ★★为什么要在**模组里**重写一遍✗★★（2026-10-01 ✓ 第③档「干活期间」的拦路石 ✓）：
    //     模组里**没有** `/dshdig` ✗（源码逐条数过 ✓）⇒ 中间层一直走**模组之外**的老 Lua 桥 ✗
    //     ★安静通道实测：发一条 `dig` ⇒ **5 分钟（314 秒）**那一格**还是 cobblestone**✗★
    //     同一个循环里 `/dshplace`（★在模组里✗★）**每次都真改了世界** ✓
    //   ⇒ ★"能改世界的动作"必须和 place 一样落在**模组侧**✗★ ✓
    /** ★★挑"对这一格最快"的那件工具✗★★（2026-10-02 ✓ 从 Lua `dig_at` 搬过来 ✓）
     *  ★口径✗★：★空手 ＝ 1.0 是原版默认✗ ⇒ 只有**更快**的工具才值得换手 ✓
     *  ★返回说明串✗★（★换没换、换到哪、快多少 ✗ 都写进回执 ✓ 便于事后复盘✓）*/
    private static String pickBestTool(ServerPlayer p,
                                       net.minecraft.world.level.block.state.BlockState st) {
        var inv = p.getInventory();
        int best = -1;
        float bestSpeed = 1.0f;
        for (int i = 0; i < 9; i++) {
            ItemStack s = inv.getItem(i);
            if (s.isEmpty()) {
                continue;
            }
            float sp = s.getDestroySpeed(st);
            if (sp > bestSpeed) {
                bestSpeed = sp;
                best = i;
            }
        }
        if (best < 0) {
            return "keep(sel=" + inv.selected + ",speed=" + String.format("%.2f", bestSpeed) + ")";
        }
        if (best == inv.selected) {
            return "same(sel=" + best + ",speed=" + String.format("%.2f", bestSpeed) + ")";
        }
        int from = inv.selected;
        inv.selected = best;
        return "switch(" + from + "->" + best + ",speed=" + String.format("%.2f", bestSpeed) + ")";
    }

    private static int digBlock(CommandContext<CommandSourceStack> ctx) throws CommandSyntaxException {
        {
            BlockPos _t = BlockPosArgument.getLoadedBlockPos(ctx, "pos");
            ServerPlayer _p = ctx.getSource().getPlayerOrException();
            ServerLevel _lv = lvl(_p);
            String _g = digGuard(_p, _lv, _t);
            if (_g != null) {
                bad(ctx.getSource(), "dshdig " + _t.toShortString() + " " + _g);
                ev("dig_refuse", "pos=" + _t.toShortString() + " why=feet_above_void");
                return 0;
            }
        }
        CommandSourceStack src = ctx.getSource();
        ServerPlayer p = src.getPlayerOrException();
        BlockPos pos = BlockPosArgument.getLoadedBlockPos(ctx, "pos");
        var level = p.serverLevel();
        double d = p.getEyePosition().distanceTo(Vec3.atCenterOf(pos));
        if (d > REACH) {
            bad(src, String.format("dshdig: too far %.2f > %.1f", d, REACH));
            return 0;
        }
        if (level.getBlockState(pos).isAir()) {
            bad(src, "dshdig: " + pos.toShortString() + " is already air - nothing to dig");
            return 0;
        }
        String was = level.getBlockState(pos).getBlock().toString();
        try {
            // ★★判据先写死✗★★（2026-10-01 ✓ 用了 oracle 才敢改 ✓）：
            //   ① 挖完那一格必须 **air**（★两把尺子都要确认 ✗ 单格扫 ✓ ＋ 原生命令 ✓★）
            //   ② ★**掉落物必须真的出现**✗★（`drops>0` ✓ —— 这是本轮的核心判据 ✓）
            //   ③ 挖的这一刻 ★`held`／`items` **都不许变**✗★（★变一个就是倒退 ✓★）
            //   ④ 走过去捡 ⇒ `items` **+1** ✓
            // ★老写法 `p.gameMode.destroyBlock(pos)` 实测 = **创造模式式清场**✗★：
            //   4/4 世界变 air ✓ 而 `drops=0` ✗ 手上也没多 ✗（★用户原话："像创造模式一样清掉也是没有掉落物的" ✓★）
            // ⇒ 改成 `level.destroyBlock(pos, true, p)` ✓：
            //   ★`true` ＝ **掉战利品**✗★ ＋ ★把 `p` 当破坏者传进去✗★ ⇒ 战利品表按**手上的工具**算 ✓
            //   （★手上拿错工具 ⇒ 本来就该不掉东西 ✗ 这正是"像玩家" ✓★）
            // ★★2026-10-02 新加：**选工具**✗★★（★从老 Lua 桥 `dig_at` 搬过来✗ ✓ 拍板＝往模组侧并 ✓）
            //   ★口径✗★：★不是"按方块名挑" ✗ 而是**按游戏自己的破坏速度**挑✗★ ——
            //     ★`ItemStack#getDestroySpeed(state)` 是**原版自己**的判断✗★
            //     ⇒ ★比名字匹配更准 ✗ 也不怕别的模组加工具 ✓★
            //   ★为什么重要✗★：★手上拿错工具 ⇒ 战利品表按**手上的**算 ✗ 本来就不该掉东西✗★
            //     ⇒ ★"挑对了"才谈得上"像玩家"✗★ ✓
            String picked = pickBestTool(p, level.getBlockState(pos));
            // ★★2.55.0✗★★（用户 2026-11-02：「**破坏方块需要有手部动画**」）
            //   ★之前这里直接 destroyBlock ✗ **没有挥手** ⇒ 从外面看是方块自己没了✗★
            //   ★挥手要在**破坏之前**发 ✗ 顺序反了就成了先没了再挥手✗★ ✓
            p.swing(net.minecraft.world.InteractionHand.MAIN_HAND, true);
            boolean broke = level.destroyBlock(pos, true, p);
            String now = level.getBlockState(pos).isAir() ? "air" : level.getBlockState(pos).getBlock().toString();
            if (!"air".equals(now)) {
                bad(src, "dshdig reason=" + (broke ? "destroyed" : "kept") + " at=" + pos.toShortString() + " was=" + was + " destroyBlock=" + broke
                        + " but now=" + now + " (★看世界真值 ✗ 不听自述 ✓★)");
                return 0;
            }
            ok(src, "dshdig " + pos.toShortString() + " was=" + was + " now=air dropped=" + broke
                    + " tool=" + picked + " held=" + p.getMainHandItem().getItem());
            evMut(pos, was, "air");        // ★★§79.412✗★ 世界变了要说✗★
            return 1;
        } catch (Throwable t) {
            bad(src, "dshdig " + pos.toShortString() + " threw " + t.getClass().getSimpleName()
                    + ": " + t.getMessage());
            return 0;
        }
    }

    private static int place(CommandContext<CommandSourceStack> ctx) throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        ServerPlayer p = src.getPlayerOrException();
        BlockPos pos = BlockPosArgument.getBlockPos(ctx, "pos");
        String item = StringArgumentType.getString(ctx, "item");
        ServerLevel level = lvl(p);
        if (p.distanceToSqr(pos.getX() + 0.5, pos.getY() + 0.5, pos.getZ() + 0.5) > (REACH + 1) * (REACH + 1)) {
            bad(src, String.format("dshplace: too far %.2f > %.1f", p.getEyePosition().distanceTo(Vec3.atCenterOf(pos)), REACH));
            return 0;
        }
        if (!level.getBlockState(pos).isAir()) {
            bad(src, "dshplace: target " + pos.toShortString() + " is not air (now "
                    + ForgeRegistries.BLOCKS.getKey(level.getBlockState(pos).getBlock()) + ")");
            return 0;
        }
        if (!ensureHeld(p, item)) {
            bad(src, "dshplace: item " + item + " not found in inventory (0..35) - nothing was placed");
            return 0;
        }
        ItemStack held = p.getMainHandItem();
        if (held.isEmpty() || !idOf(held).contains(item)) {
            bad(src, "dshplace: could not hold " + item + " (holding "
                    + (held.isEmpty() ? "empty" : idOf(held)) + ")");
            return 0;
        }
        // 六邻格里找支撑：**先找朝向玩家那一面** ✓（真人也是这么点的 ✓）
        Direction[] order = orderedFaces(p, pos);
        for (Direction d : order) {
            BlockPos sup = pos.relative(d);
            var st = level.getBlockState(sup);
            if (st.isAir() || st.getCollisionShape(level, sup).isEmpty()) {
                continue;
            }
            Direction face = d.getOpposite();          // 从支撑块看向目标格 ✓
            Vec3 hit = new Vec3(sup.getX() + 0.5 + face.getStepX() * 0.5,
                    sup.getY() + 0.5 + face.getStepY() * 0.5,
                    sup.getZ() + 0.5 + face.getStepZ() * 0.5);
            aimAt(p, hit);
            BlockHitResult bhr = new BlockHitResult(hit, face, sup, false);
            // ★★2.55.1✗★★（用户 2026-11-02：「**放置方块需要有手部动画**」）
            //   ★之前这里直接 gameMode.useItemOn ✗ 手上没有任何动作 ⇒ 方块凭空出现✗★
            //   ★挥手要在**放之前**发 ✗ 与挖掘那条一致 ✓
            p.swing(InteractionHand.MAIN_HAND, true);
            InteractionResult ir = p.gameMode.useItemOn(p, level, held, InteractionHand.MAIN_HAND, bhr);
            // ★复核**只看世界**✗：那一格原来确定是空气 ✓ 现在有方块了 ＝ 放成了 ✓
            //   （比较"是不是我手上那个方块"反而不稳 ✗：模组方块与物品 id 不一定同名 ✓
            //    所以**报出实际放下的方块名** ✓ 由调用方去判"是不是它"✓ —— 我们只保证**说真话** ✓）
            boolean placed = !level.getBlockState(pos).isAir();
            if (placed) {
                ok(src, "dshplace " + pos.toShortString() + " item=" + item + " support=" + sup.toShortString()
                        + " face=" + face.getName() + " useItemOn=" + ir + " verified="
                        + ForgeRegistries.BLOCKS.getKey(level.getBlockState(pos).getBlock())
                        + " held_now=" + (p.getMainHandItem().isEmpty() ? "empty" : idOf(p.getMainHandItem())));
                evMut(pos, "air", String.valueOf(ForgeRegistries.BLOCKS.getKey(level.getBlockState(pos).getBlock())));
                return 1;
            }
            bad(src, "dshplace: useItemOn=" + ir + " but " + pos.toShortString() + " is still "
                    + ForgeRegistries.BLOCKS.getKey(level.getBlockState(pos).getBlock())
                    + " (support " + sup.toShortString() + " face=" + face.getName() + ")");
        }
        bad(src, "dshplace: no usable support face around " + pos.toShortString()
                + " (all 6 neighbours are air or non-solid)");
        return 0;
    }

    /** 六邻面的尝试顺序 ✓：**朝向玩家的那一面先试** ✓（真人先点"自己看得见的那一面"✓） */
    private static Direction[] orderedFaces(ServerPlayer p, BlockPos pos) {
        Direction best = Direction.getNearest(p.getX() - pos.getX(), p.getY() - pos.getY(), p.getZ() - pos.getZ());
        Direction[] all = Direction.values();
        Direction[] out = new Direction[all.length];
        out[0] = best;
        int i = 1;
        for (Direction d : all) {
            if (d != best) {
                out[i++] = d;
            }
        }
        return out;
    }

    /** ★按**报价真正要的量**装料★ ✗（v2.7 ✓ 这一条同时修掉"余款"与"`paid` 说谎"✗）
     *
     * <p>为什么必须自己装 ✗：原版 `tryMoveItems` 走的是"能塞多少塞多少"✗
     * ⇒ 实测把 **16 个**绿宝石塞进付款槽 ✓ 而这一笔只要 **2** 个 ✓
     * ⇒ 余款 14 个要在关菜单时退回 ✓ 退不进去（背包满）就**掉地上** ✗✗（P20 那 25 个 ✓）
     *
     * <p>注意用 `getCostA()` ✗ **不是** `getBaseCostA()` ✓：
     * 前者是**含村民折扣的实际要价** ✓ 后者是基准价 ✗ —— 一字之差 ✓ 实测差过 2 个绿宝石 ✓
     *
     * @return 装成功了返回 true ✓（否则调用方退回 `tryMoveItems` ✓ 并如实标注 ✗）
     */
    private static boolean fillExactly(net.minecraft.world.inventory.MerchantMenu mm, ServerPlayer p, int index) {
        var o = mm.getOffers().get(index);
        return fillSlotWith(mm, p, 0, o.getCostA()) && fillSlotWith(mm, p, 1, o.getCostB());
    }

    /** 把 `want` 这一种按**正好够的数量**放进菜单的第 `slot` 号格 ✓（不够就返回 false ✓ 不硬凑 ✗） */
    private static boolean fillSlotWith(net.minecraft.world.inventory.MerchantMenu mm, ServerPlayer p,
                                        int slot, ItemStack want) {
        if (want == null || want.isEmpty()) {
            return true;                            // 这条报价不需要这一格 ✓
        }
        var paySlot = mm.getSlot(slot);
        int need = want.getCount() - paySlot.getItem().getCount();
        if (need <= 0) {
            return true;                            // 已经够了 ✓
        }
        var inv = p.getInventory();
        for (int i = 0; i < 36 && need > 0; i++) {
            ItemStack s = inv.getItem(i);
            if (s.isEmpty() || !ItemStack.isSameItemSameTags(s, want)) {
                continue;
            }
            int take = Math.min(need, s.getCount());
            ItemStack inPay = paySlot.getItem();
            if (inPay.isEmpty()) {
                paySlot.set(new ItemStack(s.getItem(), take));
            } else {
                inPay.grow(take);
                paySlot.set(inPay);                 // set 一下才会触发 `setChanged` ⇒ 结果槽会刷新 ✓
            }
            s.shrink(take);
            if (s.isEmpty()) {
                inv.setItem(i, ItemStack.EMPTY);
            } else {
                inv.setItem(i, s);
            }
            need -= take;
        }
        mm.broadcastChanges();
        return need <= 0;
    }

    private static int tradeDo(CommandContext<CommandSourceStack> ctx, int times) throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        ServerPlayer p = src.getPlayerOrException();
        Entity e = EntityArgument.getEntity(ctx, "target");
        var mm = openMerchant(src, p, e);
        if (mm == null) {
            return 0;
        }
        int index = IntegerArgumentType.getInteger(ctx, "index");
        if (index >= mm.getOffers().size()) {
            bad(src, "dshtrade: index " + index + " out of range (0.." + (mm.getOffers().size() - 1) + ")");
            p.closeContainer();
            return 0;
        }
        var o = mm.getOffers().get(index);
        // ★ 它**不返回值** ✗（`public void tryMoveItems(int)` 实测 ✓ 用 javap 从字节码里问出来的 ✓）
        //   ⇒ 所以"成了几笔"不能听它 ✓ 只能**看真值** ✗：
        //     ① 这一条报价的 `uses` 计数涨了多少 ✓ ② 玩家背包里成品多了多少 ✓✓
        int usesBefore = o.getUses();
        int haveBefore = countOf(p, idOf(o.getResult()));
        int emeraldsBefore = countOf(p, "minecraft:emerald");
        int done = 0;
        int paid = 0;                       // ★**真实扣款**（从付款槽的减少量算 ✓ 不是基准价 ✗）
        int refunded = 0;
        StringBuilder diag = new StringBuilder();
        for (int t = 0; t < times; t++) {
            // ★ 一次一笔 ✗（v2.4 的原则 ✓ 保留 ✓）：真人点两下 = 一笔 ✓ 想几笔就循环几次 ✓
            // ⚠ v2.4/v2.5 的循环体有三个坑 ✗ ⇒ v2.7 全修了 ✓：
            //   ① 放产物用错了槽号 ✗（见 `menuSlotOf` 注释 ✓ v2.5 修 ✓）
            //   ② 手持光标上若还留着东西 ✗ ⇒ 下一笔必废 ✗（v2.5 修 ✓）
            //   ③ ★**`tryMoveItems` 会搬整堆**★ ✗ ⇒ 余款一大堆 ⇒ 关菜单时退不进去就**掉地上** ✗✗
            //      （实测：付款槽被塞 16 个 ✓ 而真实成交价只有 2 ✓ 余款 14 个在路上 ✗
            //        满包那次直接 **25 个绿宝石躺地上** ✗ 见错题本 P20/P26 ✓）
            //      ⇒ v2.7 改成**自己精确装料** ✓：只搬 `getCostA()` 要的那几个 ✓
            //        装料是**真按量**的 ✓（真人也是数着放 ✓ 不是把整堆倒进去 ✗）
            mm.setSelectionHint(index);
            boolean exact = fillExactly(mm, p, index);
            if (!exact) {
                // 精确装料这条路走不通（配方结构特殊？）⇒ **退回**原版那条 ✓ 并**如实标出来** ✗
                mm.tryMoveItems(index);
            }
            int pay0 = mm.getSlot(0).getItem().getCount();
            int pay1 = mm.getSlot(1).getItem().getCount();
            int res = mm.getSlot(2).getItem().getCount();
            diag.append(" t").append(t + 1).append("{fill=").append(exact ? "exact" : "trymove")
                .append(",pay=").append(pay0).append("/").append(pay1)
                .append(",res=").append(res).append("}");
            if (mm.getSlot(2).getItem().isEmpty()) {
                diag.append("(result empty -> stop)");               // 材料不够/售罄 ⇒ 如实停 ✓
                break;
            }
            // ★ 开工前先把"光标上的残留"处理掉 ✗（v2.4 没做 ⇒ 第 2 笔废在这儿 ✓）
            if (!mm.getCarried().isEmpty()) {
                int kept = mm.getCarried().getCount();
                if (!placeCarried(mm, p)) {
                    diag.append("(carried stuck:").append(idOf(mm.getCarried())).append("x")
                        .append(kept).append(" -> stop)");
                    break;                                          // 如实停 ✓ 不硬闯 ✓
                }
                diag.append("(flushed carried ").append(kept).append(")");
            }
            int free = findFreeSlot(p);
            if (free < 0) {
                // ★ 没有空位就**别成交** ✗（成交了产物没处放 ⇒ 要么掉地上 ✗ 要么卡光标 ✗）
                diag.append("(no free slot -> stop)");
                bad(src, "dshtrade: no free inventory slot for the result - nothing was traded");
                break;
            }
            int menuSlot = menuSlotOf(mm, p, free);
            if (menuSlot < 0) {
                bad(src, "dshtrade: cannot map inventory slot " + free + " to a menu slot - aborted");
                break;
            }
            mm.clicked(2, 0, net.minecraft.world.inventory.ClickType.PICKUP, p);      // ② 拿起产物
            boolean pickedUp = !mm.getCarried().isEmpty();
            mm.clicked(menuSlot, 0, net.minecraft.world.inventory.ClickType.PICKUP, p); // ③ 放进空槽
            boolean placed = mm.getCarried().isEmpty();
            int usesNow = o.getUses();
            if (usesNow > usesBefore + done) {
                done += 1;
            }
            diag.append("{slot=").append(menuSlot).append(",got=").append(pickedUp ? 1 : 0)
                .append(",put=").append(placed ? 1 : 0).append("}");
            if (!placed) {
                // 放进去了没有 ✗ —— **当场说清楚** ✗ 别让它烂在光标上（关菜单会掉地上 ✗）
                int still = mm.getCarried().getCount();
                if (!placeCarried(mm, p)) {
                    diag.append("(STILL CARRIED:").append(idOf(mm.getCarried())).append("x")
                        .append(still).append(")");
                    break;
                }
                diag.append("(placed on retry)");
            }
        }
        int usesAfter = o.getUses();
        int haveAfter = countOf(p, idOf(o.getResult()));
        int trades = usesAfter - usesBefore;
        // ★ 真实扣款 ✗：**先把余款退回**再数 ✗（v2.7 修 ✓）
        //   v2.5 的算法是"循环一结束就数"✗ ⇒ 那一刻付款槽里正压着一大堆待退的钱 ✗
        //   ⇒ `paid` 报的是"被临时搬走的量"✗ 不是真实花费 ✗（实测 paid=16 而其实只花 2 ✗ 见 P26 ✓）
        refunded = refundPayment(src, p, mm);          // ★余款回手 ✗ 绝不许掉地上 ✗
        paid = Math.max(0, emeraldsBefore - countOf(p, "minecraft:emerald"));
        ok(src, "dshtrade do " + entityId(e) + " index=" + index
                + " trades=" + trades + " uses=" + usesAfter + "/" + o.getMaxUses()
                + " out=" + idOf(o.getResult()) + " gained=" + (haveAfter - haveBefore)
                + " paid=" + paid + " refunded=" + refunded
                + " carried=" + (mm.getCarried().isEmpty() ? "none" : idOf(mm.getCarried()))
                + " diag[" + diag.toString().trim() + "]");
        p.closeContainer();
        return trades;
    }

    /** 把光标上的东西放进任意空槽 ✓ → 成了返回 true ✓（不成 ⇒ 调用方**如实报**✗ 不许装作没事 ✗） */
    private static boolean placeCarried(net.minecraft.world.inventory.MerchantMenu mm, ServerPlayer p) {
        for (int t = 0; t < 36 && !mm.getCarried().isEmpty(); t++) {
            int free = findFreeSlot(p);
            if (free < 0) {
                return false;
            }
            int menuSlot = menuSlotOf(mm, p, free);
            if (menuSlot < 0) {
                return false;
            }
            mm.clicked(menuSlot, 0, net.minecraft.world.inventory.ClickType.PICKUP, p);
        }
        return mm.getCarried().isEmpty();
    }

    /** ★自报状态★（取代 cc0 的 `playerDetector` ✗）：一行 ASCII ✓ 好解析 ✓ */
    private static int stats(CommandContext<CommandSourceStack> ctx) throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        ServerPlayer p = src.getPlayerOrException();
        boolean creative = p.isCreative();
        ok(src, String.format(
                "dshstats name=%s pos=%.2f,%.2f,%.2f hp=%.1f food=%d xp_level=%d mode=%s "
                        + "held=%s onground=%s dim=%s",
                p.getName().getString(), p.getX(), p.getY(), p.getZ(), p.getHealth(),
                p.getFoodData().getFoodLevel(), p.experienceLevel,
                creative ? "creative" : (p.isSpectator() ? "spectator" : "survival"),
                p.getMainHandItem().isEmpty() ? "empty" : idOf(p.getMainHandItem()),
                p.onGround(), p.level().dimension().location()));
        return 1;
    }

    // ══════════════════════════════════════════════════════════════════════════
    // /dshinv —— 整理背包（真人能拖背包 ✗ 假人不能 ✓ 这里补上）
    // ══════════════════════════════════════════════════════════════════════════

    /** 槽位编号（**0 起算** ✓ 与 `bot_inv` 一致 ✓ 别搞混 1 起算的 hotbar 指令 ✗ C1 ✓） */
    private static ItemStack slotOf(ServerPlayer p, int slot) {
        if (slot >= 0 && slot < p.getInventory().getContainerSize()) {
            return p.getInventory().getItem(slot);
        }
        return ItemStack.EMPTY;
    }

    private static void setSlot(ServerPlayer p, int slot, ItemStack s) {
        if (slot >= 0 && slot < p.getInventory().getContainerSize()) {
            p.getInventory().setItem(slot, s);
        }
    }

    /** ★★§79.445✗★★：★把背包里的东西**放进容器**（★`dshtake` 的反向 ✗ 净零用✗★）✗★
     *
     *  ★口径✗★：★`put=`（★放进去几个✗★）✗ `left=`（★背包还剩几个✗★）✗ `slots_free=`**✗★
     *  ★拿不到就说为什么✗★：★`no_block_entity`／`not_a_container`／`no_match`／`container_full`**✗★ ✓
     */
    private static int invStore(CommandContext<CommandSourceStack> ctx, int want)
            throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        ServerPlayer p = src.getPlayerOrException();
        ServerLevel level = lvl(p);
        BlockPos pos = BlockPosArgument.getLoadedBlockPos(ctx, "pos");
        String item = StringArgumentType.getString(ctx, "item").trim();
        net.minecraft.world.level.block.entity.BlockEntity be = level.getBlockEntity(pos);
        if (be == null) {
            bad(src, "dshstore pos=" + pos.toShortString() + " why=no_block_entity");
            return 0;
        }
        if (!(be instanceof net.minecraft.world.Container c)) {
            bad(src, "dshstore pos=" + pos.toShortString() + " why=not_a_container kind="
                    + be.getClass().getSimpleName());
            return 0;
        }
        String wantId = item.toLowerCase(java.util.Locale.ROOT);
        var inv = p.getInventory();
        int put = 0;
        for (int i = 0; i < inv.getContainerSize() && put < want; i++) {
            ItemStack st = inv.getItem(i);
            if (st.isEmpty()) {
                continue;
            }
            String id = idOf(st);
            boolean match = id.equals(wantId) || id.endsWith(":" + wantId) || id.contains(wantId);
            if (!match) {
                continue;
            }
            int move = Math.min(st.getCount(), want - put);
            ItemStack give = st.copy();
            give.setCount(move);
            // ★先找同物品槽 ✗ 再找空槽（★与真实玩家行为一致✗★）✗★
            boolean placed = false;
            for (int k = 0; k < c.getContainerSize() && !placed; k++) {
                ItemStack dst = c.getItem(k);
                if (!dst.isEmpty() && idOf(dst).equals(id)
                        && dst.getCount() + move <= dst.getMaxStackSize()) {
                    ItemStack merged = dst.copy();
                    merged.setCount(dst.getCount() + move);
                    c.setItem(k, merged);
                    placed = true;
                }
            }
            for (int k = 0; k < c.getContainerSize() && !placed; k++) {
                if (c.getItem(k).isEmpty()) {
                    c.setItem(k, give);
                    placed = true;
                }
            }
            if (!placed) {
                bad(src, "dshstore pos=" + pos.toShortString() + " item=" + item
                        + " why=container_full put=" + put);
                return put;
            }
            ItemStack rest = st.copy();
            rest.setCount(st.getCount() - move);
            inv.setItem(i, rest.isEmpty() ? ItemStack.EMPTY : rest);
            put += move;
        }
        int leftInInv = 0;
        for (int i = 0; i < inv.getContainerSize(); i++) {
            ItemStack st = inv.getItem(i);
            if (!st.isEmpty() && idOf(st).contains(wantId)) {
                leftInInv += st.getCount();
            }
        }
        int free = 0;
        for (int k = 0; k < c.getContainerSize(); k++) {
            if (c.getItem(k).isEmpty()) {
                free++;
            }
        }
        if (put == 0) {
            bad(src, "dshstore pos=" + pos.toShortString() + " item=" + item + " why=no_match"
                    + " slots_free=" + free);
            return 0;
        }
        ok(src, "dshstore pos=" + pos.toShortString() + " item=" + item
                + " put=" + put + " left=" + leftInInv + " slots_free=" + free);
        return put;
    }

    /** ★★§79.444✗★★：★从容器取物品（★成品标准 1✗★）✗★
     *
     *  ★口径✗★：★**拿不到就说为什么** ✗ 不许"★静默 0★"✗★：
     *    `no_block_entity`／`not_a_container`／`no_match`／`inventory_full`**✗★
     *  ★匹配✗★：★全名相等 或 **短名子串**（★与 `ensureHeld` 同口径✗★）✗★
     */
    private static int invTake(CommandContext<CommandSourceStack> ctx, int want)
            throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        // ★★§79.444✗★ 与 `invList` 同款：★假玩家就是要**这条命令的执行者**✗★
        ServerPlayer p = src.getPlayerOrException();
        ServerLevel level = lvl(p);
        BlockPos pos = BlockPosArgument.getLoadedBlockPos(ctx, "pos");
        String item = StringArgumentType.getString(ctx, "item").trim();
        net.minecraft.world.level.block.entity.BlockEntity be = level.getBlockEntity(pos);
        if (be == null) {
            bad(src, "dshtake pos=" + pos.toShortString() + " why=no_block_entity");
            return 0;
        }
        if (!(be instanceof net.minecraft.world.Container c)) {
            bad(src, "dshtake pos=" + pos.toShortString() + " why=not_a_container kind="
                    + be.getClass().getSimpleName());
            return 0;
        }
        String wantId = item.toLowerCase(java.util.Locale.ROOT);
        int got = 0, slots = 0, left = 0;
        java.util.List<String> names = new java.util.ArrayList<>();
        for (int i = 0; i < c.getContainerSize() && got < want; i++) {
            ItemStack st = c.getItem(i);
            if (st.isEmpty()) {
                continue;
            }
            String id = idOf(st);
            names.add(id + "x" + st.getCount());
            boolean match = id.equals(wantId) || id.endsWith(":" + wantId) || id.contains(wantId);
            if (!match) {
                continue;
            }
            slots++;
            int take = Math.min(st.getCount(), want - got);
            ItemStack moved = st.copy();
            moved.setCount(take);
            ItemStack rest = st.copy();
            rest.setCount(st.getCount() - take);
            c.setItem(i, rest.isEmpty() ? ItemStack.EMPTY : rest);
            p.getInventory().add(moved);
            got += take;
        }
        for (int i = 0; i < c.getContainerSize(); i++) {
            ItemStack st = c.getItem(i);
            if (!st.isEmpty() && idOf(st).contains(wantId)) {
                left += st.getCount();
            }
        }
        if (got == 0) {
            bad(src, "dshtake pos=" + pos.toShortString() + " item=" + item + " why=no_match"
                    + " slots=" + c.getContainerSize() + " have[" + String.join(",", names) + "]");
            return 0;
        }
        ok(src, "dshtake pos=" + pos.toShortString() + " item=" + item
                + " got=" + got + " left=" + left + " slots=" + slots
                + " held=" + (p.getMainHandItem().isEmpty() ? "empty" : idOf(p.getMainHandItem())));
        return got;
    }

    private static int invList(CommandContext<CommandSourceStack> ctx) throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        ServerPlayer p = src.getPlayerOrException();
        StringBuilder sb = new StringBuilder("dshinv list selected=" + p.getInventory().selected + " =>");
        int n = 0;
        for (int i = 0; i < p.getInventory().getContainerSize(); i++) {
            ItemStack s = p.getInventory().getItem(i);
            if (!s.isEmpty()) {
                sb.append(" ").append(i).append(":").append(idOf(s)).append("x").append(s.getCount());
                n++;
            }
        }
        sb.append(" (").append(n).append(" used)");
        ok(src, sb.toString());
        return n;
    }

    private static int invMove(CommandContext<CommandSourceStack> ctx, int count) throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        ServerPlayer p = src.getPlayerOrException();
        int from = IntegerArgumentType.getInteger(ctx, "from");
        int to = IntegerArgumentType.getInteger(ctx, "to");
        if (from == to) {
            bad(src, "dshinv: from == to");
            return 0;
        }
        ItemStack a = slotOf(p, from).copy();
        if (a.isEmpty()) {
            bad(src, "dshinv: slot " + from + " is empty");
            return 0;
        }
        ItemStack b = slotOf(p, to).copy();
        if (b.isEmpty()) {
            int n = Math.min(count, a.getCount());
            setSlot(p, to, a.copyWithCount(n));
            a.shrink(n);
            setSlot(p, from, a);
        } else if (ItemStack.isSameItemSameTags(a, b) && b.getCount() < b.getMaxStackSize()) {
            int n = Math.min(Math.min(count, a.getCount()), b.getMaxStackSize() - b.getCount());
            b.grow(n);
            a.shrink(n);
            setSlot(p, to, b);
            setSlot(p, from, a);
        } else if (count >= a.getCount() && count >= b.getCount()) {
            setSlot(p, from, b);                       // 交换 ✓
            setSlot(p, to, a);
        } else {
            bad(src, "dshinv: cannot merge different/limited items - swap needs full stacks");
            return 0;
        }
        ok(src, "dshinv move " + from + " -> " + to + " ok");
        return 1;
    }

    /** ★这条是 I4 那个历史卡点的正解★：真人能拖背包丢东西 ✗ 假人 `drop` 只丢手持 ✗ */
    private static int invDrop(CommandContext<CommandSourceStack> ctx, int count) throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        ServerPlayer p = src.getPlayerOrException();
        int slot = IntegerArgumentType.getInteger(ctx, "slot");
        ItemStack s = slotOf(p, slot);
        if (s.isEmpty()) {
            bad(src, "dshinv: slot " + slot + " is empty");
            return 0;
        }
        int n = Math.min(count, s.getCount());
        ItemStack drop = s.copyWithCount(n);
        s.shrink(n);
        p.drop(drop, false);                            // 从**那个槽位**丢 ✓ 不是"丢手持"✗
        ok(src, "dshinv drop slot=" + slot + " " + idOf(drop) + "x" + n + " ok");
        return n;
    }

    private static int invHotbar(CommandContext<CommandSourceStack> ctx) throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        ServerPlayer p = src.getPlayerOrException();
        int slot = IntegerArgumentType.getInteger(ctx, "slot");
        ItemStack s = slotOf(p, slot).copy();
        if (s.isEmpty()) {
            bad(src, "dshinv: slot " + slot + " is empty");
            return 0;
        }
        if (slot < 9) {                                 // 已经在快捷栏 ⇒ 只是选中它 ✓
            p.getInventory().selected = slot;
            ok(src, "dshinv hotbar selected=" + slot + " (" + idOf(s) + ")");
            return 1;
        }
        int hb = p.getInventory().selected;
        ItemStack old = slotOf(p, hb).copy();
        setSlot(p, hb, s);
        setSlot(p, slot, old);
        ok(src, "dshinv hotbar swapped " + slot + " <-> " + hb + " (" + idOf(s) + ")");
        return 1;
    }

    private static int invEquip(CommandContext<CommandSourceStack> ctx) throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        ServerPlayer p = src.getPlayerOrException();
        int slot = IntegerArgumentType.getInteger(ctx, "slot");
        ItemStack s = slotOf(p, slot).copy();
        if (s.isEmpty()) {
            bad(src, "dshinv: slot " + slot + " is empty");
            return 0;
        }
        // ⚠ 1.20.1 里这个方法叫 `LivingEntity#getEquipmentSlotForItem` ✗
        //   （我第一版写成 `Mob.createEquipmentSlotForItem` ✗ —— 编译期就被挡下来了 ✓
        //    这正是"静态类型"的好处 ✓：名字错了**立刻知道** ✓ 不会静默跑偏 ✓）
        EquipmentSlot es = p.getEquipmentSlotForItem(s);
        ItemStack old = p.getItemBySlot(es).copy();
        p.setItemSlot(es, s);
        setSlot(p, slot, ItemStack.EMPTY);
        if (!old.isEmpty()) {                            // 换下来的那件放回原槽 ✓ 绝不丢 ✗
            setSlot(p, slot, old);
        }
        ok(src, "dshinv equip slot=" + slot + " -> " + es.getName() + " (" + idOf(s) + ")");
        return 1;
    }

    // ══════════════════════════════════════════════════════════════════════════
    // /dshent —— 右键实体（喂食 ✓ 繁殖 ✓ 挤奶 ✓ 剪毛 ✓ —— 真人对动物做的事）
    // ══════════════════════════════════════════════════════════════════════════

    private static int entUse(CommandContext<CommandSourceStack> ctx) throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        ServerPlayer p = src.getPlayerOrException();
        Entity target = EntityArgument.getEntity(ctx, "target");
        double dd = p.distanceTo(target);
        if (dd > REACH) {
            bad(src, String.format("dshent: too far %.2f > %.1f", dd, REACH));
            return 0;
        }
        aimAt(p, target.position().add(0, target.getBbHeight() * 0.5, 0));
        ItemStack held = p.getItemInHand(InteractionHand.MAIN_HAND);
        String hb = held.isEmpty() ? "empty" : idOf(held) + "x" + held.getCount();
        InteractionResult ir;
        try {
            ir = p.interactOn(target, InteractionHand.MAIN_HAND);
        } catch (Exception e) {
            bad(src, "dshent: server threw: " + e.getClass().getSimpleName() + " " + e.getMessage());
            return 0;
        }
        p.swing(InteractionHand.MAIN_HAND, true);
        ItemStack now = p.getItemInHand(InteractionHand.MAIN_HAND);
        ok(src, String.format("dshent use %s result=%s held %s -> %s",
                ForgeRegistries.ENTITY_TYPES.getKey(target.getType()), ir, hb,
                now.isEmpty() ? "empty" : idOf(now) + "x" + now.getCount()));
        return ir == InteractionResult.FAIL ? 0 : 1;
    }

    private static int entInfo(CommandContext<CommandSourceStack> ctx) throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        Entity e = EntityArgument.getEntity(ctx, "target");
        ok(src, String.format("dshent info %s pos=%.1f,%.1f,%.1f hp=%.1f age=%d child=%s",
                ForgeRegistries.ENTITY_TYPES.getKey(e.getType()),
                e.getX(), e.getY(), e.getZ(), e instanceof net.minecraft.world.entity.LivingEntity le ? le.getHealth() : -1f,
                e.tickCount, e instanceof net.minecraft.world.entity.AgeableMob am && am.isBaby()));
        return 1;
    }

    // ══════════════════════════════════════════════════════════════════════════
    // ★★★ v2.6：把"看"和"走"搬进模组 ★★★
    //   目标一句话 ✓：**让我（智能体）操纵它更快 ✓ 让它自己动起来更像真人 ✓**
    //   手段一句话 ✓：把"一次问一大片"和"一条指令走一整段"变成**服务端原生** ✓
    //             而不是"一格一条指令 / 一格一次扫描"✗（那正是慢与抖的根源 ✗）
    // ══════════════════════════════════════════════════════════════════════════

    /** /dshver —— 真正加载的版本 ✓（判"模组到底装上没有"✗ 以后就问它 ✓） */
    private static int ver(CommandContext<CommandSourceStack> ctx) {
        String v = ModList.get().getModContainerById("dshbridge")
                .map(c -> c.getModInfo().getVersion().toString()).orElse("unknown");
        ok(ctx.getSource(), "dshver version=" + v
                + " features=scan,digest,look,walk,events,auto,map,path,kb,kbexport,state,caps,turn,yawtrace,http"
                + ",http2,token,origin,rawmap,reqid"
                + " bot=" + esc(WATCHED)
                + " autoeat=" + AUTO_EAT + " idle=" + AUTO_IDLE);
        return 1;
    }

    /** /dshkbexport —— ★只读：把注册表里的方块 id 全列出来（§79.478✗★）✗★
     *
     * ★只读**✗ 不改任何判定** ✗ 也不改世界 ⇒ 它是"★分母★"的唯一真源 ✓
     * ★分页✗★：★每页 700 个（★桥一次回执别撑爆✗★）⇒ `total` 永远报**全量** ✓
     */
    private static int kbexport(CommandContext<CommandSourceStack> ctx, int page) {
        List<String> ids = new ArrayList<>();
        for (ResourceLocation rl : BuiltInRegistries.BLOCK.keySet()) {
            ids.add(rl.toString());
        }
        java.util.Collections.sort(ids);
        int per = 700;
        int npages = Math.max(1, (ids.size() + per - 1) / per);
        int p = Math.max(1, Math.min(page, npages));
        int from = (p - 1) * per;
        int to = Math.min(ids.size(), from + per);
        ok(ctx.getSource(), "dshkbexport total=" + ids.size() + " page=" + p + "/" + npages
                + " ids=" + String.join(",", ids.subList(from, to)));
        return 1;
    }

    /** /dshstate —— ★只读：一个方块的全部状态属性（§79.487✗★）✗★
     *
     * ★用 `BlockState.toString()`**✗ 它自带 id 和**所有**属性**（★包括模组自定义的✗★）✗
     *   ⇒ ★不认名字 ✗ 不猜属性名 ✗ 原样倒出来给大脑判✗★ ✓
     */
    private static int stateOf(CommandContext<CommandSourceStack> ctx, BlockPos pos)
            throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        ServerLevel level = lvl(src.getPlayerOrException());
        BlockState st = level.getBlockState(pos);
        BlockEntity be = level.getBlockEntity(pos);
        ok(src, "dshstate pos=" + pos.toShortString()
                + " be=" + (be == null ? "false" : "true")
                + " raw=" + st.toString().replace(" ", "_"));
        return 1;
    }

    /** /dshcaps —— ★只读：逐面探测能力接口（§79.487✗★）✗★
     *
     * ★输出的每一面✗★：★`fe=in/out/both/none` ✗ `items=y/-` ✗ `fluid=y/-`**✗★
     * ★只报**有接口**的面（★否则 6 面全打 ✗ 回执太长✗★）✗★ ✓
     */
    private static int capsOf(CommandContext<CommandSourceStack> ctx, BlockPos pos)
            throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        ServerLevel level = lvl(src.getPlayerOrException());
        BlockState st = level.getBlockState(pos);
        BlockEntity be = level.getBlockEntity(pos);
        StringBuilder sb = new StringBuilder();
        if (be == null) {
            ok(src, "dshcaps pos=" + pos.toShortString() + " be=false faces=[] "
                    + "reason=no_block_entity");
            return 1;
        }
        for (Direction d : Direction.values()) {
            String fe = "none";
            var en = be.getCapability(ForgeCapabilities.ENERGY, d);
            if (en.isPresent()) {
                var es = en.orElse(null);
                if (es != null) {
                    boolean in = es.canReceive(), out = es.canExtract();
                    fe = (in && out) ? "both" : in ? "in" : out ? "out" : "none";
                }
            }
            String it = be.getCapability(ForgeCapabilities.ITEM_HANDLER, d).isPresent() ? "y" : "-";
            String fl = be.getCapability(ForgeCapabilities.FLUID_HANDLER, d).isPresent() ? "y" : "-";
            if (!"none".equals(fe) || "y".equals(it) || "y".equals(fl)) {
                if (sb.length() > 0) sb.append(" ");
                sb.append(d.getName()).append(":fe=").append(fe)
                        .append(",items=").append(it).append(",fluid=").append(fl);
            }
        }
        ok(src, "dshcaps pos=" + pos.toShortString() + " be=" + (be == null ? "false" : "true")
                + " faces=[" + sb + "]");
        return 1;
    }

    /** 玩家所在的服务端世界 ✓（`ServerPlayer` 在 1.20.1 上没有 `serverLevel()` ✗ 用 javap 问过了 ✓） */
    private static ServerLevel lvl(ServerPlayer p) {
        return (ServerLevel) p.level();
    }

    // ══ ★★v2.15：地图读取（一条指令一张图 ✓）★★ ══════════════════════════════
    //   为什么必须放到**模组里** ✗（实测 ✓ 2026-09-23 ✓）：
    //     · 中间层用 `dshscan` 按"方块种类"批量取坐标 ⇒ 建 25x25 一片要 **42 次调用 / 36 秒** ✗
    //       （每次调用的成本几乎全是**桥的往返** 0.6 秒 ✓ 不是扫描 ✗ 扫描只要几百微秒 ✓）
    //     · 放到模组里 ⇒ **一次调用**把整片地表读出来 ✓ ⇒ 0.7 秒量级 ✓（快 50 倍 ✓）
    //   回执形状 ✓（全 ASCII ✓ 纪律③ ✓）：
    //     `dshmap box=x0,z0..x1,z1 y=70 legend=G:minecraft:grass_block,D:minecraft:dirt`
    //     然后每行 `z|GGGDD...`（每格一个字符 ✓ 同字母 = 同一种方块 ✓）
    //   ★地板判定与寻路**同一套**★ ✓（`standable` ✓）—— 不然"图说能走、走过去走不了"✗
    private static final java.util.Map<String, String> MAP_CHARS = new java.util.LinkedHashMap<>();

    private static String mapCharFor(String name) {
        if (MAP_CHARS.containsKey(name)) {
            return MAP_CHARS.get(name);
        }
        String pool = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
        String ch = MAP_CHARS.size() < pool.length()
                ? pool.substring(MAP_CHARS.size(), MAP_CHARS.size() + 1) : "#";
        MAP_CHARS.put(name, ch);
        return ch;
    }

    //   ★v2.16：补两类行★ ✗（2026-09-28 实测抓到的真 bug ✓）——
    //     现象 ✗：中间层把 `/dshmap` 解析成图后，**979 格全是"能走"** ✗
    //             而世界真值说那里地板低一格 ✗、有的格上还站着栅栏 ✗
    //     真因 ✓（模组自己明明知道 ✓ 却没说 ✗）：
    //       ① 它从 `dy=+2` 往下找到**第一个站得住的层**就停 ✓ ⇒ **只印一个字母** ✗
    //          ⇒ "那一层在第几格"**丢了** ✗ ⇒ 中间层只能瞎猜"就在脚下一格"✗
    //          ⇒ 图被**抹平** ✗ 落差全看不见 ✗（而中间层 `MAX_DOWN=3` 以内都当平路 ✗
    //            ⇒ 这正是掉虚空那一族 ✗）
    //       ② 某一格被你这一层的东西占着（栅栏/机器 ✓）⇒ 它跳过这层去找**下面**那层 ✗
    //          ⇒ **你这一层的障碍根本不出现在图里** ✗ ⇒ "图说能走、走过去被挡" ✗
    //     修法 ✓：**同一条指令多回两类行** ✓（不多花一次往返 ✓）
    //       `y<z>|`  每格一个字符 = 那一层相对**你的脚**高多少 ✓
    //                （`0` 同层 ✓ `A`/`B` = 高 1/2 ✓ `a`..`f` = 低 1..6 ✓ `.` 没找到 ✓）
    //       `b<z>|`  每格一个字符 = **你的脚层/头层**上占着的是什么方块 ✓（`.` = 空的 ✓）
    //                ★判据与 `standable` 同一套（碰撞箱 ✓ 不按方块名猜 ✓）★
    //       ★逗号分隔★ ✗（不是空格 ✗ —— 2026-09-28 栽过：中间层按空格断句 ⇒
    //        只收到第一项 `0:same` ✗ ⇒ 其余偏移全当"不知道"✗ ⇒ 图又被推平 ✗
    //        ⇒ 口径跟 `legend=` 保持一致（都是逗号 ✓）✓）
    private static final String YLEGEND =
            "0:same,A:+1,B:+2,a:-1,b:-2,c:-3,d:-4,e:-5,f:-6,.:none";

    /** v2.16：高度偏移 ⇒ 一个字符 ✓（与 `YLEGEND` 对应 ✓ 越界给 `?` ✗ 不装作知道 ✗） */
    private static char offChar(int off) {
        if (off == 0) {
            return '0';
        }
        if (off == 1) {
            return 'A';
        }
        if (off == 2) {
            return 'B';
        }
        if (off <= -1 && off >= -6) {
            return (char) ('a' + (-off - 1));
        }
        return '?';
    }

    private static int mapCmd(CommandContext<CommandSourceStack> ctx, int r) throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        ServerPlayer p = src.getPlayerOrException();
        ServerLevel lv = lvl(p);
        BlockPos c = p.blockPosition();
        MAP_CHARS.clear();
        StringBuilder head = new StringBuilder("dshmap box=")
                .append(c.getX() - r).append(',').append(c.getZ() - r).append("..")
                .append(c.getX() + r).append(',').append(c.getZ() + r)
                .append(" from=").append(c.getX()).append(',').append(c.getY()).append(',').append(c.getZ());
        java.util.List<String> rows = new java.util.ArrayList<>();
        java.util.List<String> yrows = new java.util.ArrayList<>();
        java.util.List<String> brows = new java.util.ArrayList<>();
        int stand = 0;
        int blockedCells = 0;
        for (int z = c.getZ() - r; z <= c.getZ() + r; z++) {
            StringBuilder sb = new StringBuilder();
            StringBuilder yb = new StringBuilder();
            StringBuilder bb = new StringBuilder();
            sb.append(z).append('|');
            yb.append('y').append(z).append('|');
            bb.append('b').append(z).append('|');
            for (int x = c.getX() - r; x <= c.getX() + r; x++) {
                // ★你这一层被什么占了★ ✓（v2.16）—— 碰撞箱判定 ✓ 与 `standable` 同一套 ✓
                BlockPos feet = new BlockPos(x, c.getY(), z);
                BlockPos headPos = feet.above();
                BlockPos occ = null;
                if (!lv.getBlockState(feet).getCollisionShape(lv, feet).isEmpty()) {
                    occ = feet;
                } else if (!lv.getBlockState(headPos).getCollisionShape(lv, headPos).isEmpty()) {
                    occ = headPos;
                }
                if (occ == null) {
                    bb.append('.');
                } else {
                    blockedCells++;
                    bb.append(mapCharFor(net.minecraft.core.registries.BuiltInRegistries.BLOCK
                            .getKey(lv.getBlockState(occ).getBlock()).toString()));
                }
                // 从"脚下一格之上 2 格"往下找**第一个站得住的层** ✓（近处优先 ✓ 免得画到树冠 ✓）
                BlockPos found = null;
                for (int dy = 2; dy >= -6; dy--) {
                    BlockPos f = new BlockPos(x, c.getY() + dy, z);
                    if (standable(lv, f)) {
                        found = f;
                        break;
                    }
                }
                if (found == null) {
                    sb.append('.');
                    yb.append('.');
                    continue;
                }
                stand++;
                yb.append(offChar(found.getY() - c.getY()));
                // ★★v2.17：把 `@` 那个特例删掉★★ ✗（交接 §50.7 ＋ §54.7 第 ① 条 ✓）
                //   旧行为 ✗：「能站的层**正好是假人自己那一层**」的柱子 ⇒ 只印一个 `@` ✗
                //     ⇒ **那一柱的地板方块名压根没发** ✗
                //     ⇒ 实测（§50.9 ✓）：站到平坦大平台上时 **425/458 格（93%）** 是
                //       "有地板、但不知道叫什么" ✗ ⇒ 俯视图那一整片只能画 `x` ✗
                //       —— ★用户要的"看得懂地图"其实只做到一半✗★
                //   现在 ✓：同层也照印**地板字母** ✓ —— `y<z>|` 里的偏移 `0` **本来就表示"同层"** ✓
                //     ⇒ `@` 是**冗余**的 ✓ 删掉 ⇒ 中间层那趟"只补名字"的薄扫可省 ✓
                //       （1 次调用 / 0.6~1.4 秒 ✓ 单车道稀缺 ✓）
                //   ⚠ 中间层解析器**旧版仍要能读** ✗（`@` 那条老分支留着当兜底 ✓ 不许删 ✓）
                String name = net.minecraft.core.registries.BuiltInRegistries.BLOCK
                        .getKey(lv.getBlockState(found.below()).getBlock()).toString();
                sb.append(mapCharFor(name));
            }
            rows.add(sb.toString());
            yrows.add(yb.toString());
            brows.add(bb.toString());
        }
        head.append(" blevel=").append(c.getY()).append(" blocked=").append(blockedCells)
                .append(" ylegend=").append(YLEGEND);
        StringBuilder leg = new StringBuilder();
        for (var e : MAP_CHARS.entrySet()) {
            if (leg.length() > 0) {
                leg.append(',');
            }
            leg.append(e.getValue()).append(':').append(e.getKey());
        }
        final int standFinal = stand;                 // ★lambda 只许引用"事实上的最终变量"★ ✗
        final String headLine = head.toString();      //   （`stand` 在循环里自增 ⇒ 不能直接进 lambda ✗）
        final String legLine = leg.length() == 0 ? "-" : leg.toString();
        src.sendSuccess(() -> Component.literal(headLine + " standable=" + standFinal
                + " legend=" + legLine), false);
        for (String row : rows) {
            src.sendSuccess(() -> Component.literal(row), false);
        }
        // ★v2.16：高度偏移行 ＋ "你这一层被什么占着"行★ ✓（同一条指令 ✓ 不多花往返 ✓）
        for (String row : yrows) {
            src.sendSuccess(() -> Component.literal(row), false);
        }
        for (String row : brows) {
            src.sendSuccess(() -> Component.literal(row), false);
        }
        return rows.size() + yrows.size() + brows.size() + 1;
    }

    /** ★只规划、不走★ ✓（把模组自己那条 A* 的结果**摊开给人看** ✓ 好跟中间层的规划对比 ✓） */
    private static int pathCmd(CommandContext<CommandSourceStack> ctx) throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        ServerPlayer p = src.getPlayerOrException();
        BlockPos pos = BlockPosArgument.getLoadedBlockPos(ctx, "pos");
        ServerLevel lv = lvl(p);
        long t0 = System.nanoTime();
        java.util.List<BlockPos> path = astarPath(lv, p.blockPosition(), pos);
        long ms = (System.nanoTime() - t0) / 1_000_000L;
        boolean ok = standable(lv, pos);
        StringBuilder sb = new StringBuilder("dshpath to=").append(pos.toShortString())
                .append(" goal_standable=").append(ok)
                .append(" legs=").append(path == null ? -1 : path.size())
                .append(" ms=").append(ms)
                .append(" from=").append(p.blockPosition().toShortString());
        if (path != null && !path.isEmpty()) {
            sb.append(" first=").append(path.get(0).toShortString())
                    .append(" last=").append(path.get(path.size() - 1).toShortString());
            int shown = 0;
            StringBuilder w = new StringBuilder(" waypoints=");
            for (int i = 0; i < path.size() && shown < 12; i += Math.max(1, path.size() / 12)) {
                w.append(path.get(i).toShortString()).append(' ');
                shown++;
            }
            sb.append(w);
        }
        sb.append(" reachable=").append(path != null && !path.isEmpty()
                && path.get(path.size() - 1).equals(pos));
        final String line = sb.toString();
        src.sendSuccess(() -> Component.literal(line), false);
        ev("path_plan", line);
        return 1;
    }

    /** 方块有没有碰撞箱 ✓（＝"能不能站在上面/会不会挡住"✓ 空岛安全判断全靠它 ✓） */
    private static boolean solidAt(ServerLevel level, BlockPos pos) {
        var st = level.getBlockState(pos);
        return !st.getCollisionShape(level, pos).isEmpty();
    }

    /** 把方块状态拼成 ASCII 尾巴 ✓（如 `,age=7` ✓ 全 ASCII ✗ 见纪律③ ✓） */
    private static String stateSuffix(net.minecraft.world.level.block.state.BlockState st) {
        if (st.getValues().isEmpty()) {
            return "";
        }
        StringBuilder sb = new StringBuilder();
        for (var en : st.getValues().entrySet()) {
            sb.append(',').append(en.getKey().getName()).append('=').append(en.getValue());
        }
        return sb.toString();
    }

    // ── /dshscan ──────────────────────────────────────────────────────────────
    /**
     * ★原生区域扫描★ —— 这是"读世界"从"秒级"变"微秒级"的那一步 ✗
     *
     * <p>为什么原来那么慢 ✗（实测 ✓）：CC 的 `commands.getBlockInfos` **一次只能 4³ 格** ✗
     * ⇒ 2268 格 = 42 次调用 = 3.5 s ✗；7696 格 = 120 次 = **超过 8 s 预算** ✗
     * <p>这里在 Java 里直接 `level.getBlockState` 逐格走 ✓ ⇒ 一万格也就毫秒级 ✓
     * <p>输出纪律 ✓：聚合**总是**给 ✓（省流量 ✓）；逐格 cells **只在给了 match 时**给 ✓
     * —— 因为"找小麦在哪"才是真实需求 ✓ 而"把 2268 格全列出来"是我自己受不了 ✗
     */
    private static int scan(CommandContext<CommandSourceStack> ctx, String match, int max, int page)
            throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        ServerLevel level = src.getLevel();
        BlockPos a = BlockPosArgument.getLoadedBlockPos(ctx, "from");
        BlockPos b = BlockPosArgument.getLoadedBlockPos(ctx, "to");
        int x0 = Math.min(a.getX(), b.getX()), x1 = Math.max(a.getX(), b.getX());
        int y0 = Math.min(a.getY(), b.getY()), y1 = Math.max(a.getY(), b.getY());
        int z0 = Math.min(a.getZ(), b.getZ()), z1 = Math.max(a.getZ(), b.getZ());
        long vol = (long) (x1 - x0 + 1) * (y1 - y0 + 1) * (z1 - z0 + 1);
        if (vol > 4_000_000L) {
            bad(src, "dshscan: volume too big " + vol + " (max 4000000)");
            return 0;
        }
        long t0 = System.nanoTime();
        Map<String, Integer> counts = new java.util.LinkedHashMap<>();
        List<String> hits = new ArrayList<>();
        int solid = 0, air = 0;
        boolean wantCells = match != null && !match.isEmpty();
        // ★★v2.10：`match` 支持**标签**★★ ✗（`#minecraft:logs` ✓）
        //   实测现场 ✓（2026-09-21 ✓）：`#minecraft:logs` / `#minecraft:planks` /
        //   `#minecraft:crops` 全部 `matched=0` ✗ —— 而**精确名**是好的 ✓
        //   （`minecraft:grass_block` 793 ✓ `minecraft:water` 72 ✓）
        //   ⇒ 于是"找所有原木"只能一个 id 一个 id 猜 ✗ ⇒ 这就是用户说的"感觉扫不出方块"✗
        //   实现 ✓：`#` 开头 ⇒ 解析成 `TagKey<Block>` ✓ 用 `st.is(tag)` 匹配 ✓
        //   ⚠ 标签名也给个**明确失败** ✗（解析不出来就报错 ✓ 不许悄悄返回 0 ✓）
        net.minecraft.tags.TagKey<net.minecraft.world.level.block.Block> tagKey = null;
        if (wantCells && match.startsWith("#")) {
            var tagRl = net.minecraft.resources.ResourceLocation.tryParse(match.substring(1));
            if (tagRl == null) {
                bad(src, "dshscan: bad tag " + match + " (want #namespace:path)");
                return 0;
            }
            tagKey = net.minecraft.tags.TagKey.create(
                    net.minecraft.core.registries.Registries.BLOCK, tagRl);
        }
        for (int y = y0; y <= y1; y++) {
            for (int z = z0; z <= z1; z++) {
                for (int x = x0; x <= x1; x++) {
                    BlockPos pos = new BlockPos(x, y, z);
                    var st = level.getBlockState(pos);
                    if (st.isAir()) {
                        air++;
                        continue;
                    }
                    solid++;
                    String id = ForgeRegistries.BLOCKS.getKey(st.getBlock()).toString();
                    counts.merge(id, 1, Integer::sum);
                    boolean hit = wantCells && ((tagKey != null) ? st.is(tagKey) : id.contains(match));
                    if (!hit) {
                        continue;
                    }
                    hits.add(x + "," + y + "," + z + ":" + id + stateSuffix(st));
                }
            }
        }
        long us = (System.nanoTime() - t0) / 1000L;
        int pages = Math.max(1, (hits.size() + max - 1) / max);
        int pg = Math.min(Math.max(1, page), pages);
        int from = (pg - 1) * max, to = Math.min(from + max, hits.size());
        // ★★v2.10：把种类**按数量从多到少排** ✗ ＋ 列到 40 种 ★★
        //   原来 ✗：前十种 ＋ `more_kinds=120` ✓ 而且是**扫描顺序**（y,x,z ✓）而不是多少 ✗
        //   ⇒ "这座岛整体有什么"根本问不出来 ✗（实测：kinds=130 ✓ 只看得见 10 个 ✓）
        //   ⇒ 现在 ✓：按数量降序 ✓ 列 40 种 ✓（仍有 `more_kinds=` 兜底 ✓ 不假装列全 ✗）
        final int COUNT_SHOW = 40;
        List<Map.Entry<String, Integer>> sorted = new ArrayList<>(counts.entrySet());
        sorted.sort((u, v) -> Integer.compare(v.getValue(), u.getValue()));
        StringBuilder top = new StringBuilder();
        int shown = 0;
        for (Map.Entry<String, Integer> en : sorted) {
            if (shown++ >= COUNT_SHOW) {
                top.append(",more_kinds=").append(sorted.size() - COUNT_SHOW);
                break;
            }
            if (top.length() > 0) {
                top.append(',');
            }
            top.append(en.getKey()).append(':').append(en.getValue());
        }
        StringBuilder cells = new StringBuilder();
        for (int i = from; i < to; i++) {
            if (cells.length() > 0) {
                cells.append(' ');
            }
            cells.append(hits.get(i));
        }
        // ★★§79.410✗★★：★加 `tick=` 和 `hash=`**✗★
        //   ★`tick`**✗：★这一份快照是**什么时候**的（★世界时间✗★）✗★
        //   ★`hash`**✗：★这次扫到的**内容哈希**（★名字＋数量✗★）⇒ ★Python 比较它就知道**变没变**✗★
        //   ★⇒ **不用每次重建 3D 模型** ✗ 也不会"★拿着旧快照当新世界★"✗★ ✓
        // ★★§79.414✗★★：★`hash` **含位置 ＋ 方块 ＋ 状态**✗★
        //   ★为什么✗★：★`gate-auditor`（★task-6 风险 1✗★）指出旧 hash 只算"★名字＋数量★"✗
        //   ⇒ ★**同数量异位**会误判"★没变★" ⇒ `world3d` **复用旧位置** ⇒ 模型悄悄错位✗★ ✓
        //   ★`hits` 每条就是 `"x,y,z:<id><state>"`** ⇒ ★逐条滚动就对✗★ ✓
        long _hash = 17L;
        for (String _h : hits) {
            _hash = _hash * 31L + _h.hashCode();
        }
        _hash = _hash * 31L + hits.size();
        ok(src, "dshscan box=" + x0 + "," + y0 + "," + z0 + ".." + x1 + "," + y1 + "," + z1
                + " tick=" + level.getGameTime() + " hash=" + _hash
                + " vol=" + vol + " solid=" + solid + " air=" + air + " kinds=" + counts.size()
                + " matched=" + hits.size() + " shown=" + Math.max(0, to - from) + " page=" + pg + "/" + pages
                + " us=" + us
                + " counts[" + top + "]"
                + (wantCells ? " cells[" + cells + "]" : " cells[pass a match= to list cells]"));
        return hits.size();
    }

    // ── /dshdigest ────────────────────────────────────────────────────────────
    /** ★一条指令一份态势★ —— 把"一次决策 4~6 条指令"✗压成 **1 条** ✓ */
    private static int digest(CommandContext<CommandSourceStack> ctx, double radius, double fov,
                              int listN) throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        ServerPlayer p = src.getPlayerOrException();
        ServerLevel level = lvl(p);
        var inv = p.getInventory();
        int kinds = 0, items = 0, free = 0;
        for (int i = 0; i < 36; i++) {
            ItemStack s = inv.getItem(i);
            if (s.isEmpty()) {
                free++;
            } else {
                kinds++;
                items += s.getCount();
            }
        }
        ItemStack held = p.getMainHandItem();
        AABB box = p.getBoundingBox().inflate(radius);
        List<Entity> ents = level.getEntities(p, box, en -> true);
        int hostiles = 0, drops = 0;
        double nd = -1;
        String near = "none", dropNear = "none";
        int minLeft = -1;
        // ★★2026-10-02 新增：**视野锥** ＋ **列表**✗★★（★抄外部同题项目的"可见场景" ✗ 但按玩家的方式来✓★）
        //   ★为什么要锥✗★：玩家是"看向哪就看见哪"✗ 半径球是"上帝视角"✗（用户 2026-10-01 定的方向 ✓）
        //   ★为什么默认不开✗★：`fov=360`（默认 ✓）＝ 旧行为 ✓ `list=0`（默认 ✓）＝ 旧输出 ✓
        //     ⇒ ★已有解析器与判据**一个都不受影响**✗★ ✓
        java.util.List<String> entList = new java.util.ArrayList<>();
        java.util.List<String> dropList = new java.util.ArrayList<>();
        Vec3 view = p.getViewVector(1.0F).normalize();
        double cosMin = Math.cos(Math.toRadians(fov / 2.0));
        boolean cone = fov < 359.0;
        for (Entity en : ents) {
            if (en == p) {
                continue;
            }
            double d = p.distanceTo(en);
            if (en instanceof ItemEntity ie) {
                drops++;
                int left = ie.lifespan - ie.getAge();
                if (minLeft < 0 || left < minLeft) {
                    minLeft = left;
                    dropNear = idOf(ie.getItem()) + "x" + ie.getItem().getCount();
                }
                dropList.add(idOf(ie.getItem()) + "x" + ie.getItem().getCount()
                        + "@" + String.format("%.1f", d) + "/left=" + left);
                continue;
            }
            if (cone) {          // ★只收**朝向前方 fov 度**里的✗★（★背后的不算"看见"✓★）
                Vec3 to = en.position().add(0.0, en.getBbHeight() / 2.0, 0.0)
                        .subtract(p.getEyePosition());
                if (to.length() < 0.05 || to.normalize().dot(view) < cosMin) {
                    continue;
                }
            }
            entList.add(entityId(en) + "@" + String.format("%.1f", d));
            if (en instanceof net.minecraft.world.entity.monster.Monster) {
                hostiles++;
            }
            if (nd < 0 || d < nd) {
                nd = d;
                near = entityId(en) + "@" + String.format("%.1f", d);
            }
        }
        String look = "none";
        HitResult hr = p.pick(REACH, 1.0F, false);
        if (hr instanceof BlockHitResult bhr && bhr.getType() == HitResult.Type.BLOCK) {
            look = blockName(level, bhr.getBlockPos()) + "@" + bhr.getDirection().getName()
                    + "/" + String.format("%.2f", p.getEyePosition().distanceTo(hr.getLocation()));
        } else if (hr instanceof EntityHitResult ehr) {
            look = entityId(ehr.getEntity()) + "@" + String.format("%.2f",
                    p.getEyePosition().distanceTo(ehr.getLocation()));
        }
        long gt = level.getDayTime();
        ok(src, "dshdigest reason=ok name=" + p.getName().getString()
                + String.format(" pos=%.2f,%.2f,%.2f yaw=%.1f pitch=%.1f", p.getX(), p.getY(), p.getZ(),
                        p.getYRot(), p.getXRot())
                + String.format(" hp=%.1f food=%d sat=%.1f xp=%d", p.getHealth(),
                        p.getFoodData().getFoodLevel(), p.getFoodData().getSaturationLevel(), p.experienceLevel)
                + " mode=" + (p.isCreative() ? "creative" : p.isSpectator() ? "spectator" : "survival")
                + " onground=" + p.onGround() + " dim=" + level.dimension().location()
                + " time=" + (gt % 24000L) + " day=" + (gt / 24000L)
                + " held=" + (held.isEmpty() ? "none" : idOf(held) + "x" + held.getCount())
                + " inv[x]kinds=" + kinds + ",items=" + items + ",free=" + free + ",sel=" + inv.selected
                + " ents=" + Math.max(0, ents.size() - 1) + " hostiles=" + hostiles + " nearest=" + near
                + " drops=" + drops + (drops > 0 ? ",nearest=" + dropNear + ",minleft_ticks=" + minLeft : "")
                // ★列表只在**要它**的时候才印✗★（`list>0` ⇒ 旧输出一字不变 ✓）
                + (listN > 0 ? " fov=" + String.format("%.0f", fov)
                        + " ents_list[" + capList(entList, listN) + "]"
                        + " drops_list[" + capList(dropList, listN) + "]" : "")
                + " look=" + look);
        return 1;
    }

    /** ★把列表截到 N 个 ✗ 并如实报"还有几个没列"✗★（★不许静默截断 ✗ P152 ✓★） */    private static String capList(java.util.List<String> xs, int n) {
        if (xs.isEmpty()) {
            return "none";
        }
        java.util.Collections.sort(xs);
        StringBuilder b = new StringBuilder();
        for (int i = 0; i < Math.min(n, xs.size()); i++) {
            if (i > 0) {
                b.append(";");
            }
            b.append(xs.get(i));
        }
        if (xs.size() > n) {
            b.append(";+").append(xs.size() - n);
        }
        return b.toString();
    }

    // ── /dshlook ──────────────────────────────────────────────────────────────
    /** 准星射线 ＋ **可达性** ✓ —— 真人够不着就是够不着 ✗（P16 那类静默无效的死因 ✓） */
    // ── /dshjump ★**整段删掉**✗★（2026-10-03 ✓ 欠账 ⑫ 的收尾 ✓ 见 P173 ✓）
    //   ★它曾经硬塞 `setDeltaMovement(y=0.42)` ✗ 实测 y **一点没升** ✗ 而回执照旧报 `jumps=1`✗★
    //   ⇒ ★"能跳"这件事**Carpet 自带**✗（★`/player Bot jump` ✗ 干净前提实测 71.00 → **72.00**✓★）
    //   ⇒ ★命令早已删（★`/dshjump` 报未知 ✓ 实测过✓★）✗ 今天把这个**没人调的私有方法**也清掉✗★ ✓

    // ── /dshthrow ─────────────────────────────────────────────────────────────
    /** ★把手上的一件东西**真丢到地上**✗★（★2026-10-02 ✗ 替掉会说谎/不落地的 Carpet `drop` ✓★） */
    private static int throwHeld(CommandContext<CommandSourceStack> ctx, int times)
            throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        ServerPlayer p = src.getPlayerOrException();
        int n = Math.max(1, Math.min(4, times));
        int thrown = 0;
        String what = "none";
        for (int i = 0; i < n; i++) {
            ItemStack held = p.getMainHandItem();
            if (held.isEmpty()) {
                break;
            }
            what = held.getItem().toString();
            ItemStack one = held.copy();
            one.setCount(1);
            held.shrink(1);
            // ★★这一句才是"地上真的有一件"✗★★（★`Player#drop` ＝ 原版生成掉落实体的那条路✓★）
            p.drop(one, false, true);
            thrown++;
        }
        if (thrown == 0) {
            bad(src, "dshthrow: hand is empty - nothing thrown");
            return 0;
        }
        ok(src, "dshthrow thrown=" + thrown + " item=" + what
                + " held_left=" + p.getMainHandItem().getCount()
                + " (verify on the ground with a vanilla item-entity query)");
        return 1;
    }

    // ── /dshjump ★已删除✗★（2026-10-02 ✓ 见 P173 ✓）
    //   ★它曾经硬塞 `setDeltaMovement(y=0.42)` ✗ 实测 y **一点没升** ✗ 而回执照旧报 `jumps=1`✗★
    //   ⇒ ★"能跳"这件事**Carpet 自带**✗（`/player Bot jump` ✗ 干净前提实测 71.00 → **72.00**✓★）
    //   ⇒ ★删掉它 ✗ 工具层 `jump` 走 Carpet ✓（★**不许留着一条会说谎的命令**✗ ✓★）

    // ── ★★紧围栏（欠账 ⑰ ✗ 2026-10-03✓）★★ ────────────────────────────────
    //   ★为什么必须在模组里✗★（★§79.27 实测✓★）：★中间层走 CC **一次采样 ≈ 1 秒**✗
    //     而 `move forward` 在这 1 秒里走 **5~7 格**✗ ⇒ ★它只能**事后拦**✗★
    //     （★实测：围栏 1.5 ⇒ 停在 3.03 ✗ 围栏 2.0 ⇒ 停在 6.90 ✓★）
    //   ★口径✗★：★被拦的是**每 tick** 的运动 ✗ 围栏就不能长在**每秒一次**的地方✗★ ✓
    private static volatile boolean LEASH_ON = false;
    private static double LEASH_MAX = 1.5;          // ★水平位移上限（格）✗★
    private static long LEASH_UNTIL = 0L;           // ★到点自己停（ms）✗★
    private static double LEASH_X = 0.0, LEASH_Z = 0.0;
    private static int LEASH_TICKS = 0;
    private static int LEASH_STOPS = 0;             // ★被拦过几次（★给 `status` 看✓★）
    // ★★2026-10-03 检修（欠账 ㉙）✗★★：★约束**过期之后**那些计数还留着 ✗ 于是 `status` 回
    //   `on=false` 却带 `moved=6.52 ticks=22 stops=1` ✗ ⇒ ★读的人会以为"它现在走了 6.52 格"✗★ ✓
    //   ⇒ ★修法✗★：★记下"上一次什么时候结束的"✗ ✗ 过期后的数字**一律标成"上次"**✗★ ✓
    private static long LEASH_ENDED_AT = 0L;

    /** ★每 tick 一次 ✗ 廉价（两个减法 ＋ 一次比较 ✓）✗ 越界／到点就**就地清输入**✗★ */
    private static void leashTick(net.minecraft.server.MinecraftServer server) {
        var p = server.getPlayerList().getPlayerByName(WATCHED);
        long now = System.currentTimeMillis();
        if (now >= LEASH_UNTIL) {
            boolean was = LEASH_ON;
            LEASH_ON = false;
            LEASH_ENDED_AT = now;            // ★★㉙：记下"结束的时刻"✗ 好让 `status` 标"上次"✗★
            if (p != null) {
                p.xxa = 0.0f;
                p.zza = 0.0f;
            }
            if (was) {
                ev("leash_stop", "why=duration who=" + esc(WATCHED)
                        + " moved=" + String.format("%.2f", driftOf(p)) + " max=" + LEASH_MAX
                        + " ticks=" + LEASH_TICKS);
            }
            return;
        }
        if (p == null) {
            return;
        }
        double d = driftOf(p);
        LEASH_TICKS++;
        if (d > LEASH_MAX) {
            // ★★"越界那一脚"不许发生✗★★：★这一 tick 就把输入清掉 ✗ 而且**继续清**✗★
            //   （★我们不知道走路任务会不会下一 tick 再推一次 ⇒ 不清就白拦✓★）
            p.xxa = 0.0f;
            p.zza = 0.0f;
            p.setSprinting(false);
            // ★★2026-10-03 补✗★★（★世界验收抓出来的 ✓）：★光清 `xxa/zza` **拦不住**✗★
            //   ★实测✗★：★围栏 `stops=1` 而位移到了 **14.24 格**✗★ ——
            //   ★因为 `/player <bot> move forward` 是 **Carpet 自己驱动**的✗
            //   （★它不看我们的 `xxa/zza` ✗ 它有自己的 forward 状态✓★）
            //   ⇒ ★必须同时调 **Carpet 自己的 stop**✗★：
            //     ★实测 `/player Bot stop` ⇒ 停后 1.2 秒**又挪 0.00 格**✗★ ✓
            if (LEASH_STOPS == 0) {              // ★只在**第一次**越界时发 ✗ 免得每 tick 刷✓★
                try {
                    server.getCommands().performPrefixedCommand(
                            server.createCommandSourceStack(), "player " + WATCHED + " stop");
                } catch (Throwable ignored) {
                    // ★Carpet 不在／名字变了 ⇒ 事件里照样记 ✗ 也别影响游戏✓★
                }
            }
            LEASH_STOPS++;
            ev("leash_stop", "why=fence who=" + esc(WATCHED)
                    + " moved=" + String.format("%.2f", d) + " max=" + LEASH_MAX
                    + " tick=" + LEASH_TICKS);
            LEASH_UNTIL = now;                       // ★一拦就到期 ⇒ 之后每 tick 继续清输入✓★
        }
    }

    /** ★离起点的**水平**位移✗★（★竖直不算 ✗ 掉下去是另一条闸✓★） */
    private static double driftOf(ServerPlayer p) {
        if (p == null) {
            return 0.0;
        }
        double dx = p.getX() - LEASH_X;
        double dz = p.getZ() - LEASH_Z;
        return Math.sqrt(dx * dx + dz * dz);
    }

    private static int leashArm(CommandContext<CommandSourceStack> ctx, double maxDrift, int seconds)
            throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        ServerPlayer p = src.getPlayerOrException();
        LEASH_MAX = Math.max(0.1, maxDrift);
        LEASH_X = p.getX();
        LEASH_Z = p.getZ();
        LEASH_TICKS = 0;
        LEASH_STOPS = 0;
        LEASH_UNTIL = System.currentTimeMillis() + Math.max(1, seconds) * 1000L;
        LEASH_ON = true;
        ok(src, "dshleash armed max_drift=" + String.format("%.2f", LEASH_MAX)
                + " seconds=" + Math.max(1, seconds) + " from=" + String.format("%.2f,%.2f", LEASH_X, LEASH_Z)
                + " (it stops inputs IN-TICK on breach; why= appears as an ascii event)");
        return 1;
    }

    private static int leashStatus(CommandContext<CommandSourceStack> ctx) throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        ServerPlayer p = src.getPlayerOrException();
        long left = LEASH_UNTIL - System.currentTimeMillis();
        // ★★`moved` 的**口径**要说清✗★★（2026-10-03 ✓）：★没装过约束时它是
        //   "离原点(0,0)的距离"✗ ⇒ ★看起来像"走了 4119 格"✗ ✗ 那是**误导**✗★
        //   ⇒ ★没量过（`ticks=0`）就报 `moved=n/a`✗★ ✓
        String mv = (LEASH_TICKS > 0) ? String.format("%.2f", driftOf(p)) : "n/a";
        // ★★2026-10-03（欠账 ㉙）✗★★：★过期的数字要**标成"上次"** ✗ 并给出"多久之前"✗★ ✓
        boolean stale = (!LEASH_ON) && (LEASH_ENDED_AT > 0);
        long ago = stale ? Math.max(0L, System.currentTimeMillis() - LEASH_ENDED_AT) : 0L;
        ok(src, "dshleash reason=ok on=" + LEASH_ON + " max_drift=" + String.format("%.2f", LEASH_MAX)
                + " left_ms=" + Math.max(0L, left) + " moved=" + mv
                + " ticks=" + LEASH_TICKS + " stops=" + LEASH_STOPS
                + (stale ? (" ★上次★ ended_ago_ms=" + ago
                            + "（★这些计数是**上一次**的 ✗ 不是现在✓★）") : ""));
        return 1;
    }

    private static int leashOff(CommandContext<CommandSourceStack> ctx) throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        ServerPlayer p = src.getPlayerOrException();
        LEASH_ON = false;
        LEASH_UNTIL = System.currentTimeMillis();
        LEASH_ENDED_AT = System.currentTimeMillis();   // ★㉙：手动关也算"结束"一次 ✓
        p.xxa = 0.0f;
        p.zza = 0.0f;
        ok(src, "dshleash off (inputs cleared)");
        return 1;
    }

    private static int look(CommandContext<CommandSourceStack> ctx, double reach) throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        ServerPlayer p = src.getPlayerOrException();
        ServerLevel level = lvl(p);
        HitResult hr = p.pick(reach, 1.0F, false);
        if (hr instanceof BlockHitResult bhr && bhr.getType() == HitResult.Type.BLOCK) {
            BlockPos bp = bhr.getBlockPos();
            var st = level.getBlockState(bp);
            double d = p.getEyePosition().distanceTo(hr.getLocation());
            String sfx = stateSuffix(st);
            ok(src, String.format("dshlook block=%s pos=%d,%d,%d face=%s dist=%.2f reachable=%s state[%s]",
                    ForgeRegistries.BLOCKS.getKey(st.getBlock()).toString(),
                    bp.getX(), bp.getY(), bp.getZ(), bhr.getDirection().getName(), d, d <= REACH,
                    sfx.isEmpty() ? "none" : sfx.substring(1)));
            return 1;
        }
        if (hr instanceof EntityHitResult ehr) {
            double d = p.getEyePosition().distanceTo(ehr.getLocation());
            ok(src, String.format("dshlook entity=%s dist=%.2f reachable=%s",
                    entityId(ehr.getEntity()), d, d <= REACH));
            return 2;
        }
        ok(src, String.format("dshlook none dist=%.2f (aimed at air within %.1f blocks)", reach, reach));
        return 0;
    }

    // ── /dshwalk ──────────────────────────────────────────────────────────────
    /** 走路任务 ✓（一个玩家一份 ✓ 逐 tick 推进 ✓ 走完留一会儿让 `/dshwalk` 读到结果 ✓） */

    // ★★v2.23（§79.392）✗★★：★`dshgoto` —— 一次给**一串路点** ✗ tick 里**连续走**✗★★
    //   ★为什么进模组✗★：★Python ↔ CC 一条 **0.6 秒** ✗ 一格一发 ⇒ **一格一顿**✗★ ⇒
    //   ★一次给一串 ✗ 模组在 tick 里连着走（★这就是参考项目的"胡萝卜追逐"那层✗★）✗★ ✓
    // ══ ★★v2.26（§79.407）✗★★：`dshdo` —— **模组侧动作队列**（★实时世界判每一步✗★）★★
    //   ★为什么进模组✗★（用户拍板 ✗ 2026-10-26）★：
    //     ★Python 侧一条命令 **0.6 秒**（★CC 轮询 500ms ＋ HTTP✗★）⇒
    //       ★"★执行器★"放在外面 ⇒ **每步都可能对不上世界**（★§79.405 头上放原石／§79.406 漏记账✗★）✗★
    //     ★⇒ ★**执行**必须在**同进程**里 ✗ 每 tick 用**实时**世界判 ✓ Python 只当**大脑**（★出计划✗★）✗★ ✓
    //   ★取舍✗★：★**内部复用现有命令**（★`dshwalk`／`dshdig`／`dshplace`／`dshuse`✗★）✗★
    //     ⇒ ★不重复任何逻辑 ✗ 行为与命令行**完全一致**（★护栏／挑工具／掉落／世界核验全都在✓★）✗★ ✓
    //   ★判成没成✗★：★**看世界**（`level.getBlockState`）✗ 不看命令回包✗★ ✓
    private static final class DoStep {
        final String kind;            // walk / dig / place / use / wait
        final BlockPos pos;           // 除 wait 外都要
        final String arg;             // place 的 item ／ use 的 face ／ wait 的 ticks
        DoStep(String kind, BlockPos pos, String arg) {
            this.kind = kind; this.pos = pos; this.arg = arg;
        }
    }

    private static final class DoTask {
        // ★★§79.442✗★★：★**动作类型**（★规划说了算 ✗ 运行时别再猜✗★）✗★
        //   ★`jump:`／`parkour:` ⇒ `forceJump`（★一定起跳✗★）✗★
        //   ★`drop:` ⇒ `forceNoJump`（★一定不跳 ✗ 免得下坡乱蹦✗★）✗★
        boolean forceJump = false;
        boolean forceNoJump = false;
        final java.util.List<DoStep> steps;
        int idx = 0;
        int ticks = 0;               // 当前步已等几 tick
        boolean walkIssued = false;
        long deadlineTick = 0;
        final java.util.List<String> log = new java.util.ArrayList<>();
        DoTask(java.util.List<DoStep> steps) { this.steps = steps; }
    }

    /** ★★§79.436✗★ 最近一次 walk 的运动统计（★do_done／do_fail 共用✗★）✗★ */
    private static volatile String lastMoveStats =
            "dist=0.00 t=0 spd=0.00 sprint=0 jumps=0 look=0";
    private static final Map<UUID, DoTask> DOS = new ConcurrentHashMap<>();
    private static final int DO_STEP_TICKS = 240;     // ★单步上限 12 秒✗★

    private static int doStart(CommandContext<CommandSourceStack> ctx) throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        ServerPlayer p = src.getPlayerOrException();
        String raw = StringArgumentType.getString(ctx, "plan");
        java.util.List<DoStep> steps = new java.util.ArrayList<>();
        for (String part : raw.split(";")) {
            String s = part.trim();
            if (s.isEmpty()) {
                continue;
            }
            int c = s.indexOf(':');
            if (c <= 0) {
                bad(src, "dshdo reason=bad_step_format（要 kind:...）：" + s);
                return 0;
            }
            String kind = s.substring(0, c).trim().toLowerCase();
            String rest = s.substring(c + 1).trim();
            if ("wait".equals(kind)) {
                steps.add(new DoStep("wait", null, rest));
                continue;
            }
            // ★★§79.415✗★★：★split(":", 2)**✗ —— ★旧写法 split(":") 会把
            //   place:x,y,z:minecraft:cobblestone 的 **item 截成 minecraft**✗★
            //   ⇒ ★ensureHeld **子串**匹配到任意物品 ⇒ **放错方块**✗★（★task-5 实测✓★）✗★
            //   ★只切**第一段** ⇒ item 里带 : 也原样保留 ✓✗★
            String[] v = rest.split(":", 2);
            String[] xyz = v[0].split(",");
            if (xyz.length != 3) {
                bad(src, "dshdo reason=bad_pos：" + s);
                return 0;
            }
            try {
                BlockPos pos = new BlockPos(Integer.parseInt(xyz[0].trim()),
                        Integer.parseInt(xyz[1].trim()), Integer.parseInt(xyz[2].trim()));
                String arg = v.length > 1 ? v[1] : null;
                steps.add(new DoStep(kind, pos, arg));
            } catch (NumberFormatException e) {
                bad(src, "dshdo reason=bad_number：" + s);
                return 0;
            }
        }
        if (steps.isEmpty()) {
            bad(src, "dshdo reason=no_steps");
            return 0;
        }
        ServerLevel level = lvl(p);
        DoTask t = new DoTask(steps);
        t.deadlineTick = level.getGameTime() + DO_STEP_TICKS;
        DOS.put(p.getUUID(), t);
        ev("do_start", "n=" + steps.size() + " from=" + p.blockPosition().toShortString());
        ok(src, "dshdo start n=" + steps.size() + " from=" + p.blockPosition().toShortString());
        return 1;
    }

    private static int doStatus(CommandContext<CommandSourceStack> ctx) {
        CommandSourceStack src = ctx.getSource();
        ServerPlayer p;
        try {
            p = src.getPlayerOrException();
        } catch (CommandSyntaxException e) {
            bad(src, "dshdo reason=needs_player status");
            return 0;
        }
        DoTask t = DOS.get(p.getUUID());
        if (t == null) {
            ok(src, "dshdo status idle");
            return 1;
        }
        DoStep cur = t.idx < t.steps.size() ? t.steps.get(t.idx) : null;
        ok(src, "dshdo status idx=" + t.idx + "/" + t.steps.size()
                + " cur=" + (cur == null ? "-" : (cur.kind + (cur.pos == null ? "" : "@" + cur.pos.toShortString())))
                + " ticks=" + t.ticks + " log=[" + String.join("|", t.log) + "]");
        return 1;
    }

    private static int doStop(CommandContext<CommandSourceStack> ctx) {
        CommandSourceStack src = ctx.getSource();
        try {
            ServerPlayer p = src.getPlayerOrException();
            DoTask t = DOS.remove(p.getUUID());
            WALKS.remove(p.getUUID());
            ok(src, "dshdo stop" + (t == null ? " (idle)" : " (done " + t.idx + ")"));
            ev("do_stop", "idx=" + (t == null ? -1 : t.idx));
            return 1;
        } catch (CommandSyntaxException e) {
            bad(src, "dshdo reason=needs_player stop");
            return 0;
        }
    }

    /** ★给假人在**模组内部**执行一条命令（★和命令行同一条路 ✗ 不重复逻辑✗★）✗★ */
    private static boolean execCmd(ServerPlayer p, String cmd) {
        // ★★§79.409✗★★：★**必须给权限**✗★ —— ★假玩家**不是 OP** ⇒
        //   ★`requires(s -> s.hasPermission(PERM))` **直接拒** ⇒ `performPrefixedCommand` **返回 0 而不抛**✗★
        //   ★⇒ 命令**静默没执行**（★2026-10-27 实测：dshdo 里 dshwalk 一点没动✗★）✗★ ✓
        CommandSourceStack src = p.createCommandSourceStack()
                .withSuppressedOutput().withPermission(4);
        try {
            int rc = p.getServer().getCommands().performPrefixedCommand(src, cmd);
            if (rc <= 0) {
                // ★★§79.402✗★ 返回码 0 ⇒ **记下来** ✗ 不许静默（★这就是`dshwalk`没动的病灶✗★）✗★
                ev("do_cmd_err", "cmd=" + cmd + " rc=" + rc);
                return false;
            }
            return true;
        } catch (Throwable t) {          // ★★§79.402✗★ 内部命令抛了也要吵✗★
            ev("do_cmd_err", "cmd=" + cmd + " err=" + t.getClass().getSimpleName()
                    + ":" + String.valueOf(t.getMessage()));
            return false;
        }
    }

    /** ★一步做完没有✗★：★看**世界** ✗ 不看回包（★§79.406 的教训✗★）✗★ */
    private static boolean stepDone(ServerPlayer p, ServerLevel level, DoStep s) {
        if (s.pos == null) {
            return true;
        }
        var st = level.getBlockState(s.pos);
        switch (s.kind) {
            case "dig":
                return st.isAir();
            case "place":
                return !st.isAir();
            case "walk": {
                // ★★§79.409✗★★：★**正好那一格** ✗ 不用 ±1 ✗★
                //   ★教训✗★：★±1 ⇒ 第一步（★人还在 z=11 ✗ 目标 z=12✗★）**差 1 就判"到了"**✗
                //   ⇒ **假成功** ✗ 后面全乱 ✗（★2026-10-27 实测✗★）✗★ ✓
                return p.blockPosition().equals(s.pos);
            }
            default:
                return true;
        }
    }

    private static void doFail(ServerPlayer p, DoTask t, String why) {
        DoStep cur = t.idx < t.steps.size() ? t.steps.get(t.idx) : null;
        // ★★§79.436✗★ 失败也带（★半路卡住时的统计一样有用✗★）
        WalkTask _wt2 = WALKS.get(p.getUUID());
        lastMoveStats = _wt2 != null ? _wt2.moveStats() : lastMoveStats;
        ev("do_fail", "idx=" + t.idx + " step=" + (cur == null ? "-" : cur.kind) + " why=" + why
                + " move=" + lastMoveStats);
        DOS.remove(p.getUUID());
        WALKS.remove(p.getUUID());
    }

    // ══ ★★§79.431✗★★：`dshdo` 的**每种动作一个处理函数**（★纯重构 ✗ 行为逐字节不变✗★）★★
    //   ★为什么拆✗★：★`tickDo` 原来**一个方法**里同时管 wait／walk（★span 合并 ＋ 可站校验 ＋
    //     建 WalkTask ＋ 超时✗★）／dig／place／use／stepDone／advance／do_fail ✗ 而且里面
    //     §79. 引用 **9 次**✗★ ⇒ ★每加一种地形就要改它 ✗ 改一处漏一处✗★
    //     （★§79.430 就是这么漏的：`openDoorAt` 补了第一道校验 ✗ 漏了 span 扫描✗★）✓
    //   ★纪律✗★：★事件名／日志格式／失败原因字符串**一个字节都不许改**✗★（★判据靠它们✗★）✓
    //   ★"这一格能不能走"只有**一处**判据✗★：`canWalkInto()` ✓
    //     （★第一道校验 `walk_target_not_standable` 与 span 扫描 `walk_no_standable_span` 都调它✗★）

    /** ★这一格"能不能走"✗★ —— ★**唯一**判据✗★（★§79.430 的根：两个地方各写一套 ⇒ 漏一处✗★）
     *
     *  ★四种"能走"✗★：
     *    ★`standable`（★站得下人：脚下有非岩浆地板 ＋ 脚层空 ＋ 头层空✗★）
     *    ★`closedDoorAt`（★关着的门算能过 ✗ 走到跟前自动开✗★）
     *    ★`openDoorAt`（★开着的门**也要算**✗★ —— ★§79.429：门一开 `standable` 反而假 ⇒ 出不了屋✗★）
     *  ★门要看**脚格与头格**两层（★门是上下半格✗★）✓
     */
    private static boolean canWalkInto(ServerLevel level, BlockPos pos) {
        return standable(level, pos)
                || closedDoorAt(level, pos) || closedDoorAt(level, pos.above())
                || openDoorAt(level, pos) || openDoorAt(level, pos.above());
    }

    /** ★这条 dshdo 跑完了✗★（★事件 ＋ 清账 ✗ 与原来内联的两行**逐字节相同**✗★） */
    private static void doDone(ServerPlayer p, DoTask t) {
        // ★★§79.436✗★ 完成时把**运动统计**一起报（★先赋值 ✗ 再发事件✗★）
        WalkTask _wt = WALKS.get(p.getUUID());
        lastMoveStats = _wt != null ? _wt.moveStats() : lastMoveStats;
        ev("do_done", "n=" + t.steps.size() + " at=" + p.blockPosition().toShortString()
                + " log=" + String.join("|", t.log)
                + " move=" + lastMoveStats);
        DOS.remove(p.getUUID());
    }

    private static void tickDo(ServerPlayer p) {
        DoTask t = DOS.get(p.getUUID());
        if (t == null) {
            return;
        }
        ServerLevel level = lvl(p);
        long now = level.getGameTime();
        if (t.idx >= t.steps.size()) {
            doDone(p, t);
            return;
        }
        DoStep s = t.steps.get(t.idx);
        switch (s.kind) {
            case "wait" -> tickWait(p, t, s);
            case "walk" -> tickWalkStep(p, t, s, level, now);
            case "dig" -> tickDig(p, t, s, level);
            case "place" -> tickPlace(p, t, s, level);
            case "use" -> tickUse(p, t, s, level);
            // ★★§79.442✗★★：★**四个动作类型**（★全是 `walk` 的变体 ✗ 不复制执行代码✗★）✗★
            case "jump", "drop", "parkour", "open_door" -> tickMoveTyped(p, t, s, level, now);
            default -> doFail(p, t, "unknown_kind=" + s.kind);
        }
    }

    /** ★★§79.442✗★★：★**动作类型**的执行入口✗★

     *  ★做法✗★：★`jump`／`parkour` ⇒ `forceJump`** ✗ ★`drop` ⇒ `forceNoJump`**✗★
     *  ★`open_door` ⇒ 先 `dshuse`**（★复用现成命令 ✗ 不重写开门✗★）✗★
     *  ★然后把这一步**改写成 `walk`** 交给 `tickWalkStep`** —— ★执行路径只有一条**✗★ ✓
     *  ★（★"★一个动作一开关 ✗ 不复制代码★" ✗ 免得又出现"★改一处漏一处★"✗★）✗★ ✓
     */
    private static void tickMoveTyped(ServerPlayer p, DoTask t, DoStep s, ServerLevel level, long now) {
        if (!t.walkIssued) {
            t.forceJump = "jump".equals(s.kind) || "parkour".equals(s.kind);
                // sec 79.454: a drop: step must only forbid the DOWN jumps.
                //   Measured: drop-on-flat -> jumps=0 (works); but drop-to-a-higher
                //   cell FAILed because the required step-up jump was forbidden too.
                //   Generic rule (no block names): forbid only when the target is
                //   NOT higher than the current feet cell.
                t.forceNoJump = "drop".equals(s.kind)
                        && s.pos.getY() <= p.blockPosition().getY();
            if ("open_door".equals(s.kind)) {
                boolean rc = execCmd(p, "dshuse " + s.pos.getX() + " " + s.pos.getY() + " "
                        + s.pos.getZ() + " up");
                ev("do_open", "pos=" + s.pos.toShortString() + " rc=" + rc);
            }
            t.steps.set(t.idx, new DoStep("walk", s.pos, null));
            tickWalkStep(p, t, t.steps.get(t.idx), level, now);
            return;
        }
        tickWalkStep(p, t, s, level, now);
    }

    /** ★wait 步✗★：★等够 n tick ⇒ 记一条 `wait<n>=ok`✗★ */
    private static void tickWait(ServerPlayer p, DoTask t, DoStep s) {
        int n = 1;
        try {
            n = Integer.parseInt(s.arg == null ? "1" : s.arg.trim());
        } catch (NumberFormatException e) {   // ★★§79.402✗★ 坏参数要吵✗★
            ev("do_cmd_err", "wait 参数坏=" + s.arg);
        }
        t.ticks++;
        if (t.ticks >= Math.max(1, n)) {
            t.log.add("wait" + n + "=ok");
            advance(t);
        }
    }

    /** ★walk 步✗★：★span 合并 ＋ 可走校验 ＋ 建 `fixedRoute` WalkTask ＋ 超时✗★ 全在这一个函数里 */
    private static void tickWalkStep(ServerPlayer p, DoTask t, DoStep s, ServerLevel level,
                                     long now) {
        if (!t.walkIssued) {
            // ★发之前**实时验**一次可走（★§79.405 那一族的教训✗★）✗★
            // ★★§79.429／§79.430✗★★：★**唯一判据** `canWalkInto`✗★
            //   （★关着的门＋**开着的门**都算能走✗★ —— ★§79.429：house_nav 跑完门是开的✗
            //     ⇒ 原来只判 standable／closedDoor ⇒ 回程 `walk_target_not_standable`✗★）✓
            if (!canWalkInto(level, s.pos)) {
                doFail(p, t, "walk_target_not_standable@" + s.pos.toShortString());
                return;
            }
            // ★★§79.417✗★★：★**不发 `dshwalk`** ✗ 直接建 `fixedRoute` 的 `WalkTask`**✗★
            //   ★为什么✗★：★`dshwalk` 走**模组自己的 A\*** ⇒ ★会自己绕路／跑偏✗★
            //   ★⇒ ★一旦跑偏 ✗ 后面**绝对坐标**的路点全对不上（★`house_nav` 5/8 实测✗★）✗★
            //   ★`fixedRoute=true` ＋ 单路点 ⇒ `tickWalk` **只朝这一个点走 ✗ 不重规划**✗★
            //   ★（★`dshgoto` 就是这个机制 ✗ 它从没跑偏过✓★）✗★ ✓
            // ★★§79.427✗★★：★**把连续 walk 合并成一条真路径**✗★
            //   ★为什么✗★：★一格一个 WalkTask ⇒ `tickWalk` 的 `t.sprint = dist > 4.0` **永远假**
            //     ⇒ **从不疾跑** ✗ 而且每格都重新起步／重瞄准 ⇒ **走起来一顿一顿**✗★
            //   ★做法✗★：★往后扫连续的 walk 步 ✗ 只要目标可走就收进 `route`**✗
            //     ★遇到不可走的 ⇒ **停在上一格**（★不硬塞 ✗ 免得整条路被判死✗★）✗★
            //     ★然后把这段**替换成 1 个 walk 步**（★`pos` ＝ 最后一格✗★）
            //     ⇒ ★`stepDone`／日志／超时**全都不用改**✗★ ✓
            java.util.LinkedList<BlockPos> route = new java.util.LinkedList<>();
            int span = 0;
            BlockPos lastOk = s.pos;
            while (t.idx + span < t.steps.size()) {
                DoStep sk = t.steps.get(t.idx + span);
                if (!"walk".equals(sk.kind)) {
                    break;                       // ★后面不是走 ⇒ 停✗★
                }
                // ★★§79.430 的根在这一行被消灭✗★★：★span 扫描**与第一道校验调同一个判据**✗★
                //   （★2.33.0 的 span 只判 standable／closedDoorAt ⇒ **漏了 openDoorAt**
                //     ⇒ ★门一开就 break ⇒ 路径空 ⇒ `walk_no_standable_span` ⇒ 人关在屋里✗★）✓
                if (!canWalkInto(level, sk.pos)) {
                    break;                       // ★这格走不了 ⇒ 只走到上一格✗★
                }
                route.add(sk.pos);
                lastOk = sk.pos;
                span++;
            }
            if (route.isEmpty()) {
                doFail(p, t, "walk_no_standable_span@" + s.pos.toShortString());
                return;
            }
            if (span > 1) {
                // ★把 span 个 walk 步换成 1 个（★end 那格✗★）✗★
                for (int _z = 0; _z < span; _z++) {
                    t.steps.remove(t.idx);
                }
                t.steps.add(t.idx, new DoStep("walk", lastOk, null));
                ev("do_span", "cells=" + span + " to=" + lastOk.toShortString());
            }
            long now0 = level.getGameTime();
            long perStep = Math.max(DO_STEP_TICKS, DO_STEP_TICKS / 2L * span);
            WalkTask wt = new WalkTask(lastOk.getX(), lastOk.getY(), lastOk.getZ(),
                    now0 + perStep, false, p.getX(), p.getZ(), now0);
            wt.fixedRoute = true;
            wt.path = route;
            wt.pathIdx = 0;
            wt.goalReachable = true;
            // ★★§79.442✗★ 把 DoTask 的动作开关**抄给 WalkTask**（★tickWalk 里判的是 WalkTask✗★）
            wt.forceJump = t.forceJump;
            wt.forceNoJump = t.forceNoJump;
            WALKS.put(p.getUUID(), wt);
            t.walkIssued = true;
            t.ticks = 0;
            t.deadlineTick = now + perStep;
            return;
        }
        t.ticks++;
        if (stepDone(p, level, s)) {
            t.log.add("walk@" + s.pos.toShortString() + "=ok");
            WALKS.remove(p.getUUID());
            advance(t);
            return;
        }
        if (now > t.deadlineTick) {
            doFail(p, t, "walk_timeout@" + s.pos.toShortString()
                    + " at=" + p.blockPosition().toShortString());
        }
    }

    /** ★挖一格✗★（★`dshdig` ✗ 同步执行 ⇒ 立刻看世界判成没成✗★） */
    private static void tickDig(ServerPlayer p, DoTask t, DoStep s, ServerLevel level) {
        syncStep(p, t, s, level,
                "dshdig " + s.pos.getX() + " " + s.pos.getY() + " " + s.pos.getZ());
    }

    /** ★放一格✗★（★`dshplace` ✗ §79.407：put 之前**实时护栏** —— 不许放在脚／头／支撑上✗★） */
    private static void tickPlace(ServerPlayer p, DoTask t, DoStep s, ServerLevel level) {
        String cmd = "dshplace " + s.pos.getX() + " " + s.pos.getY() + " " + s.pos.getZ()
                + " \"" + (s.arg == null ? "minecraft:cobblestone" : s.arg) + "\"";
        // ★★§79.407✗★★：★**put 之前实时护栏**（★place 不许放在脚／头／支撑上✗★）✗★
        BlockPos feet = p.blockPosition();
        if (s.pos.equals(feet) || s.pos.equals(feet.above()) || s.pos.equals(feet.below())) {
            doFail(p, t, "place_on_body@" + s.pos.toShortString());
            return;
        }
        syncStep(p, t, s, level, cmd);
    }

    /** ★对着一格用一次✗★（★`dshuse` ✗ 门／活板门／栅栏门✗★） */
    private static void tickUse(ServerPlayer p, DoTask t, DoStep s, ServerLevel level) {
        syncStep(p, t, s, level,
                "dshuse " + s.pos.getX() + " " + s.pos.getY() + " " + s.pos.getZ()
                        + " " + (s.arg == null ? "up" : s.arg));
    }

    /** ★dig／place／use 的共同尾巴✗★：★执行 ⇒ 数 tick ⇒ 看**世界**判成没成 ⇒ 给 3 tick 宽限✗★ */
    private static void syncStep(ServerPlayer p, DoTask t, DoStep s, ServerLevel level,
                                 String cmd) {
        execCmd(p, cmd);
        t.ticks++;
        if (stepDone(p, level, s)) {
            t.log.add(s.kind + (s.pos == null ? "" : "@" + s.pos.toShortString()) + "=ok");
            advance(t);
            return;
        }
        if (t.ticks > 3) {                    // ★给 3 tick 让世界更新✗★
            doFail(p, t, s.kind + "_not_done@" + s.pos.toShortString());
        }
    }

    private static void advance(DoTask t) {
        // ★★§79.442✗★★：★**动作类型的开关必须清零**✗★
        //   ★不然 jump: 的 forceJump 会漏到后面每一步 ⇒ 整条路都在乱蹦✗★ ✓
        t.forceJump = false;
        t.forceNoJump = false;
        t.idx++;
        t.ticks = 0;
        t.walkIssued = false;
    }

    private static int gotoStart(CommandContext<CommandSourceStack> ctx) throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        ServerPlayer p = src.getPlayerOrException();
        ServerLevel level = lvl(p);
        String raw = StringArgumentType.getString(ctx, "route");
        java.util.LinkedList<BlockPos> route = new java.util.LinkedList<>();
        for (String part : raw.split(";")) {
            String[] v = part.trim().split(",");
            if (v.length != 3) {
                bad(src, "dshgoto reason=bad_point_format（要 x,y,z;x,y,z）: " + part);
                return 0;
            }
            try {
                route.add(new BlockPos(Integer.parseInt(v[0].trim()),
                        Integer.parseInt(v[1].trim()), Integer.parseInt(v[2].trim())));
            } catch (NumberFormatException e) {
                bad(src, "dshgoto reason=bad_number: " + part);
                return 0;
            }
        }
        if (route.isEmpty()) {
            bad(src, "dshgoto reason=no_points");
            return 0;
        }
        for (BlockPos q : route) {
            if (!standableOrOpenDoor(level, q)) {
                bad(src, "dshgoto reason=no_stand at=" + q.toShortString() + " 站不住（★不去撞虚空✗★）");
                ev("goto_refuse", "bad=" + q.toShortString());
                return 0;
            }
        }
        BlockPos last = route.getLast();
        long now = level.getGameTime();
        WalkTask t = new WalkTask(last.getX(), last.getY(), last.getZ(), now + 1200, false,
                p.getX(), p.getZ(), now);
        t.fixedRoute = true;
        t.path = route;
        t.pathIdx = 0;
        t.goalReachable = true;
        WALKS.put(p.getUUID(), t);
        ev("goto_start", "n=" + route.size() + " to=" + last.toShortString());
        ok(src, "dshgoto start n=" + route.size() + " to=" + last.toShortString()
                + " from=" + String.format("%.2f,%.2f,%.2f", p.getX(), p.getY(), p.getZ()));
        return 1;
    }

    // ★★v2.23（§79.392）✗★ 挖之前的**脚下护栏**✗★★
    //   ★规则（★用户 2026-10-25 定✗★）：★要挖的是**脚下那块** ✗ 而它**下面是空** ⇒ **拒绝**✗★
    //   ★为什么✗★：★挖掉 ⇒ **人直接掉下去**（★空岛掉虚空真死过✗★）✗★ ✓
    private static String digGuard(ServerPlayer p, ServerLevel lv, BlockPos target) {
        BlockPos feet = p.blockPosition();
        BlockPos support = feet.below();
        if (!target.equals(support)) {
            return null;
        }
        if (!lv.getBlockState(support.below()).getCollisionShape(lv, support.below()).isEmpty()) {
            return null;
        }
        return "★拒绝✗★：要挖的是**脚下那一块** ✗ 而它**下面是空**✗（★挖了就掉虚空✗★）";
    }

    private static final class WalkTask {
        boolean fixedRoute = false;   // ★★v2.23（§79.392）★ 路点表：**禁掉重规划** ✓
        int pillarTicks = 0;      // ★★v2.22（§79.386）★ 1by1tower 计数 ✓
        final double tx, ty, tz;
        final long endTick;
        final boolean exact;
        int mode = 0;          // 0=未知 ✓ 1=移动输入（`xxa/zza`）✓ 2=直接 `move()` ✓
        int noProgress = 0;
        double lastX, lastZ;
        boolean done = false;
        long doneTick = 0;
        double atX, atY, atZ;
        String how = "", why = "";
        // ★v2.7 新增的三个"如实记账"字段★ ✓（绕障 ✓ 下台阶 ✓ 疾跑 ✓ —— 都要报出来 ✗ 不许藏着 ✓）
        int detours = 0;
        int detourDir = 0;
        int detourTicks = 0;
        int stepDowns = 0;
        boolean sprint = false;
        // ★v2.8.1：**认准一边**✗ —— v2.7.1 的绕障每次都重新挑边 ⇒ **左右横跳、原地打转** ✗
        //   实测 ✓：8 次绕障、910 tick 之后又回到 z≈9.5 ✗（5.6 秒的侧步**全抵消** ✗）
        //   ⇒ 真人贴墙走是"**认准一个方向走到底**"✓（墙走完了自然就过去了 ✓）
        int detourSide = 0;          // 本任务**锁定**的绕障方向（0 = 还没定 ✓）
        int freeTicks = 0;           // 连续"走得动"多久 ⇒ 够久了就解锁方向 ✓（免得绕完还一直贴墙 ✗）
        // ★★v2.9：A* 路线（"优化地图路线选取"✓）★★
        //   实测三现场（都是坐标级证据 ✓ 见 logs/terrain_map.txt 与 logs/floor_scan.txt ✓）：
        //   ① 岛内本身**就有 3 层高差**（草方块同时在 y=68/69/70 ✗）
        //      而 v2.8 的 `walkableAt` 只按**自己那一层**判四向 ✗ ⇒ 一格台阶被判"走不过"✗
        //   ② 一旦离地（掉下去 / 被顶起来 ✗）⇒ 四向全判"站不住" ⇒ 报 `blocked` ✗
        //      —— **把"我在空中"当成了"我被挡住了"** ✗✗（实测 `4131,72,9` ✓）
        //   ③ 目标可能在**岛外**（全岛可站面 x 最大 4138 ✗ 而它被要求去 4150 ✗）
        //      ⇒ 该报 **unreachable ＋ 最近能到的那个点** ✗ 而不是走一半说 blocked ✗
        //   ⇒ 所以：**搜一条真路** ✓ 支持 跳上 1 格 / 落下 ≤3 格 / 避开岩浆 ✓
        java.util.List<BlockPos> path = null;   // 路径（不含起点 ✓ 第一格就是"下一步"✓）
        int pathIdx = 0;                        // 走到第几格了 ✓
        int replans = 0;                        // 重规划次数 ✓（"卡了就重算"✓）
        boolean goalReachable = false;          // ★目标到底能不能到★ ✗（不可达时**如实报**✓）
        BlockPos nearest = null;                // 目标不可达时：**最近能到的那个可站格** ✓
        int stuck = 0;                          // 连续没推进多少 tick ✓（触发重规划 ✓）
        boolean inWater = false;               // ★v2.13：这一刻在水里吗★ ✗（游泳要用 ✓）
        // ★★§79.436✗★★：★**运动统计**（★用户要求"★别全靠眼睛★"✗★）✗★
        int jumps = 0;
        int sprintTicks = 0;
        int lookChanges = 0;
        double dist = 0.0;
        int motionTicks = 0;
        double statPX = Double.NaN, statPZ = Double.NaN, statPY = Double.NaN;
        float statYaw = Float.NaN;
        // ★★§79.442✗★★：★动作类型开关（★`tickWalk` 的 `t` 是 **WalkTask** ✗ 所以加这✗★）✗★
        boolean forceJump = false;
        boolean forceNoJump = false;
        // ★★2.44.0（§79.476）✗★★：★走路**不许偷偷放方块**✗★
        //   实测：一次"走过去"里 `walk_pillar` 放了个 grass_block ⇒ 又摔了 1 点血 ⇒
        //   又少了 1 个物品 ✗ 而回执只说 `reached` ✓ 规划层（§79.471）已经不用 pillar 了
        //   ⇒ 执行层这套副本默认**关掉** ✗ 并且**如实上报**次数 ✓
        static boolean ALLOW_PILLAR = false;
        int pillarPlaced = 0;

        /** ★可读统计（★放进事件 ✗ 判据能直接断言✗★）✗★ */
        String moveStats() {
            double secs = motionTicks / 20.0;
            double spd = secs > 0.05 ? dist / secs : 0.0;
            return String.format(java.util.Locale.ROOT,
                    "dist=%.2f t=%d spd=%.2f sprint=%d jumps=%d look=%d",
                    dist, motionTicks, spd, sprintTicks, jumps, lookChanges);
        }
        // ★v2.7：把**耗时**也记下来 ✓ —— 不然"变快了吗"只能靠外部拿秒表量 ✗
        //   （我上一次就是这么量的 ✗ 还把每 0.35 秒一次的轮询往返也算进去了 ✗ 见 P27 ✓）
        final long startTick;
        final double fromX, fromZ;

        WalkTask(double tx, double ty, double tz, long endTick, boolean exact, double sx, double sz) {
            this.tx = tx; this.ty = ty; this.tz = tz;
            this.endTick = endTick; this.exact = exact;
            this.lastX = sx; this.lastZ = sz;
            this.startTick = -1;
            this.fromX = sx; this.fromZ = sz;
        }

        WalkTask(double tx, double ty, double tz, long endTick, boolean exact, double sx, double sz,
                 long startTick) {
            this.tx = tx; this.ty = ty; this.tz = tz;
            this.endTick = endTick; this.exact = exact;
            this.lastX = sx; this.lastZ = sz;
            this.startTick = startTick;
            this.fromX = sx; this.fromZ = sz;
        }
    }

    // ══ ★★v2.9：局部网格 A*（"优化地图路线选取"✓）★★ ════════════════════════
    // 设计要点（每一条都对应一个实测现场 ✓ 见上面 WalkTask 里的三条 ✗）：
    //   · 节点 = **站得住的格** ✓（脚层空 ✓ 头层空 ✓ 脚下有支撑 ✓ 支撑不是岩浆 ✗）
    //   · 相邻 = 水平 8 向 × { 同层 ✓ 跳上 1 格 ✓ 落下 1~3 格 ✓ }
    //   · 斜走**不许切角** ✗（要求两个正交邻格也通 ✓）—— 不然会卡在墙角里 ✗
    //   · 代价 ✓：直走 1.0 ｜ 斜走 1.414 ｜ 跳上 +0.6 ｜ 落下 +0.2×格数
    //   · 搜不动就**退化为"离目标最近的可站格"** ✓ 并让上层**如实报 unreachable** ✗
    //   · ★只搜局部★ ✗（水平半径 30 ✓ 垂直 ±7 ✓ 上限 8000 节点 ✓）
    //     —— 全图搜会卡主线程 ✓ 而这段是**每 tick 都可能重算**的 ✓
    private static final int[][] ASTAR_DIRS8 = {
            {1, 0}, {-1, 0}, {0, 1}, {0, -1}, {1, 1}, {1, -1}, {-1, 1}, {-1, -1}};
    private static final int[] ASTAR_DY = {0, 1, -1, -2, -3};
    // ★★v2.17：执行闸与 A* 的**落差口径必须同一套**★★ ✗（P140 的真根因 ✓ 见交接 §61.5 第 1 条 ✓）
    //   旧代码 ✗：`ASTAR_DY` 允许降 1~3 格 ✗ 而每 tick 的执行闸**只认降 1 格** ✗
    //     ⇒ A* 规划出来的第一步（降 2 格）被执行器**当场否决** ✗
    //     ⇒ `result=edge` ＋ 位移 0.00 ＋ 一个航点都不推进 ✗
    //     ⇒ ★安全规则把人**关在桶顶上**✗★（P124「安全规则能关住人」一族 ✓）
    //   ⇒ 现在两处**同一个数**✦：`MAX_DROP` 就是 `ASTAR_DY` 里最深那一档 ✓（改一个要一起改 ✗）
    private static final int MAX_DROP = 3;
    // ★牢笼放宽时的**硬上限**✗★（＝ `dshmap` 往下找地板的范围 6 格 ✓）—— ★绝不走进真虚空✗★
    private static final int MAX_DROP_HARD = 6;
    private static final int[][] ASTAR_DIRS4 = {{1, 0}, {-1, 0}, {0, 1}, {0, -1}};   // ★v2.15 贴边判定用 ✓
    private static final int ASTAR_R = 30;
    private static final int ASTAR_DY_R = 7;
    private static final int ASTAR_MAX_NODES = 20000;      // ★v2.15：3000 → 20000★ ✗
    //   实测（2026-09-23 ✓）：预算太小 ⇒ 搜到一半就收工 ⇒ 拿"离目标最近的那半截路"当结果 ✗
    //   ⇒ 表现成：走两步就"到达失败/被挡"⇒ 重规划 ⇒ 原地打转 ✗（实测一段 12 格走了 32 秒 ✗）
    //   代价 ✓：A* 是**纯内存＋已缓存的碰撞形状** ✓ 2 万节点仍是毫秒级 ✓ 不会卡 tick ✓
    private static final long ASTAR_NS_BUDGET = 12_000_000L;   // ★3ms → 12ms★ ✗（同上 ✓）
    // ★贴边惩罚★ ✗（2026-09-23 加了它 ✓ 因为**假人掉进过虚空**✗）：
    //   空岛上"能站"不等于"安全" ✗ —— 紧贴平台边缘走 ⇒ 一点惯性/一点偏差就下去了 ✗
    //   ⇒ 给"旁边就是没地板的格子"加代价 ✓ ⇒ 找出来的路自然**离边远一点** ✓
    private static final double ASTAR_EDGE_PENALTY = 0.9;
    // ★★v2.11.2：**时间预算**★★ ✗ —— 这段跑在**服务器 tick 线程**上 ✓
    //   为什么会"整机卡一下"✗（用户提问 ✓ 我自首 ✓）：
    //     上限几千节点 × 每节点 ~40 次方块/碰撞查询 ⇒ 单次重规划可能几十毫秒 ✗
    //     而**单机版里"游戏主线程卡"就是"整个客户端卡"** ✓ ⇒ 表现成整机卡顿 ✓
    //   ⇒ 现在每次最多 **3 毫秒** ✓ 到点就带着"当前最优"退出 ✓
    //     ★宁可不完美 ✓ 也别卡住游戏★ ✗（下一个 tick 还会重规划 ✓ 不是放弃 ✓）
    //   ★v2.15 起预算改成 12ms★ ✓（常量在 ASTAR_MAX_NODES 上面那块 ✓ 别在这里重复声明 ✗）

    /** 优先队列元素 ✓（按 f 排 ✓） */
    private static final class AstarNode implements Comparable<AstarNode> {
        final BlockPos p;
        final double f;

        AstarNode(BlockPos p, double f) {
            this.p = p;
            this.f = f;
        }

        @Override
        public int compareTo(AstarNode o) {
            return Double.compare(this.f, o.f);
        }
    }

    /** 那一格"脚下有地板"吗 ✓ 且地板**不是岩浆** ✗
     *
     *  ★★v2.17：还要认"碰撞箱**顶有多高**"★★ ✗（P140 §5.2 ✓ 有实测现场 ✓）
     *    旧写法 ✗：只判"碰撞箱非空" ✗ ⇒ **薄板被当成一整格地板** ✗
     *      实测 ✓：站在 `computercraft:wireless_modem_normal`（薄板）上真值 `y=72.19` ✓
     *              而 `dshmap` 说那一列能站在 **`y=73`** ✗ ⇒ 层模型**偏高 0.81 格** ✗
     *    ⚠ **阈值 0.5 是故意选的** ✗：★为的是**零回归**✗★ ——
     *      · `>= 0.5`（整格 1.0 / 耕地 0.9375 / 灵魂沙 0.875 / **半砖 0.5**）⇒ **与旧行为完全一致** ✓
     *        （`slab_ramp_test` 的 R2「半步全接受」正靠这条 ✓ 动它会连累整条电池 ✗）
     *      · `< 0.5`（地毯 0.0625 / 雪层 0.125 / **薄板** ✓）⇒ 以前被当整格 ⇒ 现在**如实判"不是地板"** ✓
     *    ★"半格也能走"那套是**中间层**的 `pathplan.is_auto_step`（★默认关 ✗★）—— 不在这层管 ✓
     */
    private static boolean floorOk(ServerLevel lv, BlockPos feet) {
        BlockPos below = feet.below();
        net.minecraft.world.level.block.state.BlockState b = lv.getBlockState(below);
        var shape = b.getCollisionShape(lv, below);
        if (shape.isEmpty()) {
            return false;
        }
        if (b.getBlock() == net.minecraft.world.level.block.Blocks.LAVA) {
            return false;
        }
        // ★v2.17：顶面太矮 ⇒ 它是**薄板/地毯/雪层** ✗ 不是这一层的整格地板 ✗（见方法注释里的阈值理由 ✓）
        return shape.max(net.minecraft.core.Direction.Axis.Y) >= 0.5;
    }

    /** ★v2.17 新增★：从 `feet` 这一格往前，**第一个实心面在几格之下** ✗
     *  返回值 ＝ **落差格数**（0 ＝ 同层平地 ✓ 1 ＝ 一格台阶 ✓ …）｜ **-1 ＝ 真虚空** ✗
     *  ★为什么必须是"逐层找"而不是"看下面两格"✗★：旧的 `below()` / `below(2)` **只认降 1 格** ✗
     *   ⇒ 与 `ASTAR_DY`（允许降 3 格）**自相矛盾** ⇒ 这就是 P140 ✓（见 `MAX_DROP` 那段注释 ✓）
     */
    private static int landingDrop(ServerLevel lv, BlockPos feet, int maxK) {
        for (int k = 1; k <= maxK; k++) {
            if (solidAt(lv, feet.below(k))) {
                return k - 1;
            }
        }
        return -1;
    }

    /** ★v2.17 新增★：问一句"**我现在出不出去**" ✗（P124 纪律① ✓）
     *  四邻有没有**任何**一格按正常规则能走 ✓ 一个都没有 ⇒ 这是**牢笼** ✗ ⇒ 不许拦 ✓
     *  ⚠ 它只在"**本来要拒绝**"那一条分支上被调用 ✓（正常每 tick 不花这个钱 ✓）
     */
    private static boolean lockedIn(ServerLevel lv, ServerPlayer p) {
        BlockPos base = BlockPos.containing(p.getX(), p.getY(), p.getZ());
        int[][] dirs = {{1, 0}, {-1, 0}, {0, 1}, {0, -1}};
        for (int[] d : dirs) {
            BlockPos f = base.offset(d[0], 0, d[1]);
            if (!passable2(lv, f)) {
                continue;
            }
            int dd = landingDrop(lv, f, MAX_DROP + 1);
            if (dd >= 0 && dd <= MAX_DROP) {
                return false;                    // 有一格能走 ⇒ 不是牢笼 ✓
            }
        }
        return true;
    }

    /** 那一格"站得下人"吗 ✓（＝脚下有非岩浆地板 ✓ ＋ 脚层空 ✓ ＋ 头层空 ✓） */
    private static boolean standable(ServerLevel lv, BlockPos feet) {
        BlockPos head = feet.above();
        if (!lv.getBlockState(feet).getCollisionShape(lv, feet).isEmpty()) {
            return false;
        }
        if (!lv.getBlockState(head).getCollisionShape(lv, head).isEmpty()) {
            return false;
        }
        return floorOk(lv, feet);
    }

    /** "身上过得去"吗 ✓（只看脚层与头层空不空 ✓ 不要求有地板 ✓）—— 用于防切角与下落通道 ✓ */
    private static boolean passable2(ServerLevel lv, BlockPos feet) {
        BlockPos head = feet.above();
        return lv.getBlockState(feet).getCollisionShape(lv, feet).isEmpty()
                && lv.getBlockState(head).getCollisionShape(lv, head).isEmpty();
    }

    // ══ ★★v2.20（★§79.363✗★）✗★★：★门类 —— 让**A\* 认识门** ✗ 让**走路会开门**✗★ ★★
    //   ★为什么✗★：★原版 `standable` 只看**碰撞盒** ✗ 于是"★关着的门★"＝墙 ✗
    //     ⇒ 屋里屋外**明明有门** ✗ A* 却说"★不可达★"（★2026-10-24 实测✗★）✗★ ✓
    //   ★口径✗★：★关着的门 **算能过** ✗ 但要**加代价**（★开门要时间✗★）✗ 走到跟前**自动开**✗★ ✓
        private static boolean doorLike(net.minecraft.world.level.block.state.BlockState st) {
        net.minecraft.world.level.block.Block b = st.getBlock();
        if (b instanceof net.minecraft.world.level.block.DoorBlock
                || b instanceof net.minecraft.world.level.block.FenceGateBlock
                || b instanceof net.minecraft.world.level.block.TrapDoorBlock) {
            return true;
        }
        // ★★v2.25（§79.399）✗★★：★**模组门**（★`chipped:sliding_dark_oak_door` 之类✗★）✗
        //   ★它们**不是**原版 `DoorBlock` ✗ 于是 `doorLike` 一直**不认**✗★
        //   ⇒ `closedDoorAt`／`openDoorAt` 全失败 ⇒ `dshgoto` **拒绝穿门**✗★ ✓
        //   ★名字判据✗★：★`door` 或 `gate` 在 id 里 ⇒ 算门 ✗ 但**排除 `trapdoor`**✗★
        //   （★活板门"开"的时候是**地板** ✗ 不能当门✓★）✗★ ✓
        String id = net.minecraft.core.registries.BuiltInRegistries.BLOCK.getKey(b).toString();
        if (id.contains("trapdoor")) {
            return false;
        }
        return id.contains("door") || id.contains("gate");
    }

    private static boolean closedDoorAt(ServerLevel lv, BlockPos pos) {
        net.minecraft.world.level.block.state.BlockState st = lv.getBlockState(pos);
        if (!doorLike(st)) {
            return false;
        }
        if (st.hasProperty(net.minecraft.world.level.block.state.properties.BlockStateProperties.OPEN)) {
            return !st.getValue(net.minecraft.world.level.block.state.properties.BlockStateProperties.OPEN);
        }
        // ★模组门读不到 OPEN ⇒ 只要**有碰撞**就当"关着"✓
        return !st.getCollisionShape(lv, pos).isEmpty();
    }

    // ★★v2.24（§79.398）✗★★：★"能站 **或** 是**开着的门**"（★`dshgoto` 的路点校验用✗★）✗★
    //   ★为什么✗★：★开着的模组门**可能仍报碰撞盒**（★上半那半✗★）⇒ 普通 `standable` 判"站不住"
    //   ⇒ `dshgoto` **整条路被拒** ✗ 而门明明 `open=true`（★2026-10-26 实测✗★）✗★ ✓
    private static boolean openDoorAt(ServerLevel lv, BlockPos pos) {
        net.minecraft.world.level.block.state.BlockState st = lv.getBlockState(pos);
        if (!doorLike(st)) {
            return false;
        }
        if (st.hasProperty(net.minecraft.world.level.block.state.properties.BlockStateProperties.OPEN)) {
            return st.getValue(net.minecraft.world.level.block.state.properties.BlockStateProperties.OPEN);
        }
        return st.getCollisionShape(lv, pos).isEmpty();
    }

    private static boolean standableOrOpenDoor(ServerLevel lv, BlockPos feet) {
        if (standable(lv, feet)) {
            return true;
        }
        if (!floorOk(lv, feet)) {
            return false;
        }
        BlockPos head = feet.above();
        if (openDoorAt(lv, feet) || openDoorAt(lv, head)) {
            return true;
        }
        // ★★v2.25（§79.399）✗★★：★**模组门**的 `open` 可能是它**自己的属性名**✗
        //   ⇒ `hasProperty(BlockStateProperties.OPEN)` 假 ⇒ 上面那行判不出来✗★
        //   ★这一条最稳✗★：★"★脚或头是门类方块 ✗ 且脚下有地板★" ⇒ **放行**✗★
        //   ★执行器**先 `dshuse` 开门** ✗ 走到跟前时门已经开了 ✓（★没开的话走路 tick 也会开✓★）✗★ ✓
        if (doorLike(lv.getBlockState(feet)) || doorLike(lv.getBlockState(head))) {
            return true;
        }
        return false;
    }

    /** ★"能站 **或** 是关着的门（打开后能站）"✗ —— **只给 A* 用**✓（其它地方口径不动 ✓）★ */
    private static boolean standableOrDoor(ServerLevel lv, BlockPos feet) {
        if (standable(lv, feet)) {
            return true;
        }
        if (!floorOk(lv, feet)) {
            return false;
        }
        BlockPos head = feet.above();
        boolean fDoor = closedDoorAt(lv, feet);
        boolean hDoor = closedDoorAt(lv, head);
        boolean fOpen = lv.getBlockState(feet).getCollisionShape(lv, feet).isEmpty();
        boolean hOpen = lv.getBlockState(head).getCollisionShape(lv, head).isEmpty();
        return (fDoor || fOpen) && (hDoor || hOpen) && (fDoor || hDoor);
    }

    /** ★走到门口就**把门打开**✓（原版置 OPEN ✗ 模组门走 use ✗） */
    private static void tryOpenDoor(ServerPlayer p, ServerLevel lv, BlockPos aim) {
        if (aim == null) {
            return;
        }
        for (BlockPos q : new BlockPos[]{aim.below(), aim, aim.above()}) {
            net.minecraft.world.level.block.state.BlockState st = lv.getBlockState(q);
            if (!doorLike(st)) {
                continue;
            }
            if (st.hasProperty(net.minecraft.world.level.block.state.properties.BlockStateProperties.OPEN)) {
                if (st.getValue(net.minecraft.world.level.block.state.properties.BlockStateProperties.OPEN)) {
                    continue;
                }
                lv.setBlock(q, st.setValue(net.minecraft.world.level.block.state.properties.BlockStateProperties.OPEN, true), 3);
                for (BlockPos nb : new BlockPos[]{q.above(), q.below()}) {
                    net.minecraft.world.level.block.state.BlockState s2 = lv.getBlockState(nb);
                    if (s2.getBlock() == st.getBlock()
                            && s2.hasProperty(net.minecraft.world.level.block.state.properties.BlockStateProperties.OPEN)) {
                        lv.setBlock(nb, s2.setValue(net.minecraft.world.level.block.state.properties.BlockStateProperties.OPEN, true), 3);
                    }
                }
                ev("walk_door", "opened=" + q.toShortString());
                continue;
            }
            try {
                st.use(lv, p, net.minecraft.world.InteractionHand.MAIN_HAND, new net.minecraft.world.phys.BlockHitResult(
                        net.minecraft.world.phys.Vec3.atCenterOf(q),
                        net.minecraft.core.Direction.UP, q, false));
                ev("walk_door", "used=" + q.toShortString());
            } catch (Exception e) {
                ev("walk_door", "use_failed=" + q.toShortString());
            }
        }
    }

    /** 启发式 ✓：水平八向距离（octile ✓）＋ 垂直加重 ✓（可采纳 ✓ 不会高估 ✓） */
    private static double astarH(BlockPos a, BlockPos b) {
        int dx = Math.abs(a.getX() - b.getX()), dz = Math.abs(a.getZ() - b.getZ());
        int lo = Math.min(dx, dz), hi = Math.max(dx, dz);
        return (hi - lo) + 1.4142 * lo + 1.2 * Math.abs(a.getY() - b.getY());
    }

    /** 人（假人）在半空时 ✗：就近找一个**站得住的格** ✓ —— 这就是"先落地"✓ */
    private static BlockPos nearestStandable(ServerLevel lv, BlockPos from, int r) {
        for (int dy = 0; dy >= -5; dy--) {
            for (int dx = -r; dx <= r; dx++) {
                for (int dz = -r; dz <= r; dz++) {
                    BlockPos c = from.offset(dx, dy, dz);
                    if (standable(lv, c)) {
                        return c;
                    }
                }
            }
        }
        return null;
    }

    /** ★搜路★ ✓ 返回"从起点之后的那些格"✓（搜不到目标 ⇒ 返回**离目标最近**那条路的末尾段 ✓） */
    private static java.util.List<BlockPos> astarPath(ServerLevel lv, BlockPos from, BlockPos goal) {
        BlockPos start = standable(lv, from) ? from : nearestStandable(lv, from, 3);
        if (start == null) {
            return null;
        }
        // ★★v2.15：搜索框要**同时罩住起点和终点**★★ ✗
        //   老代码只算 `|c - goal| > ASTAR_R` ✗ ⇒ 起点离目标超过 30 格时，
        //   连**起点的邻居**都被判出界 ✗ ⇒ 一步都扩不出去 ⇒ 返回空路 ⇒
        //   回执写 `reachable=false` ⇒ **"假 unreachable"** ✗（实测：很多次"明明走得过去"✗）
        //   ⇒ 现在：框 = 起点终点包围盒 ＋ 每边 8 格余量 ✓（A* 只在局部搜，仍然不拖 tick ✓）
        final int bx0 = Math.min(start.getX(), goal.getX()) - 8;
        final int bx1 = Math.max(start.getX(), goal.getX()) + 8;
        final int bz0 = Math.min(start.getZ(), goal.getZ()) - 8;
        final int bz1 = Math.max(start.getZ(), goal.getZ()) + 8;
        boolean goalOk = standable(lv, goal);
        java.util.HashMap<Long, Double> gScore = new java.util.HashMap<>();
        java.util.HashMap<Long, Long> came = new java.util.HashMap<>();
        java.util.PriorityQueue<AstarNode> open = new java.util.PriorityQueue<>();
        gScore.put(start.asLong(), 0.0);
        open.add(new AstarNode(start, astarH(start, goal)));
        BlockPos best = start;
        double bestH = astarH(start, goal);
        int seen = 0;
        BlockPos found = null;
        long tPlan = System.nanoTime();          // ★时间预算起点 ✓（见 ASTAR_NS_BUDGET ✓）
        while (!open.isEmpty() && seen++ < ASTAR_MAX_NODES) {
            if ((System.nanoTime() - tPlan) > ASTAR_NS_BUDGET) {
                break;                           // 到点就收 ✓ 带"当前最优"回去 ✓ **不卡游戏** ✗
            }
            BlockPos cur = open.poll().p;
            double h = astarH(cur, goal);
            if (h < bestH) {
                bestH = h;
                best = cur;
            }
            if (cur.equals(goal) && goalOk) {
                found = cur;
                break;
            }
            double cg = gScore.getOrDefault(cur.asLong(), 1e9);
            for (int[] d : ASTAR_DIRS8) {
                for (int dy : ASTAR_DY) {
                    BlockPos c = cur.offset(d[0], dy, d[1]);
                    if (c.getX() < bx0 || c.getX() > bx1 || c.getZ() < bz0 || c.getZ() > bz1
                            || Math.abs(c.getY() - goal.getY()) > ASTAR_DY_R) {
                        continue;                        // ★只在"起点终点那一带"里搜★ ✓（v2.15 ✓）
                    }
                    boolean diag = d[0] != 0 && d[1] != 0;
                    // ★★v2.20（§79.363）✗★ 门**算能过** ✗ 代价 +2.0 ✗★
                    if (!standableOrDoor(lv, c)) {
                        continue;
                    }
                    boolean needOpen = closedDoorAt(lv, c) || closedDoorAt(lv, c.above());
                    if (diag && !(passable2(lv, cur.offset(d[0], dy, 0))
                            || passable2(lv, cur.offset(0, dy, d[1])))) {
                        continue;                        // 防切角 ✓（至少一侧要过得去 ✓）
                    }
                    if (dy > 0 && !passable2(lv, cur.above(2))) {
                        continue;                        // 跳上去得**头顶两层都空** ✓
                    }
                    if (dy < 0) {
                        boolean clear = true;
                        for (int k = -1; k > dy; k--) {
                            if (!passable2(lv, cur.offset(d[0], k, d[1]))) {
                                clear = false;
                                break;
                            }
                        }
                        if (!clear) {
                            continue;                    // 下落通道要通 ✓
                        }
                    }
                    double cost = (diag ? 1.4142 : 1.0) + (dy > 0 ? 0.6 : (dy < 0 ? 0.2 * (-dy) : 0.0))
                            + (needOpen ? 2.0 : 0.0);          // ★★开门代价 ✗ 与 Python 侧一致✗★★
                    // ★v2.15：贴边惩罚★ ✓ —— 四邻里有"站不住"的格子 ⇒ 加代价 ✓
                    //   空岛上"能站"≠"安全" ✗（2026-09-23 假人真的掉下去过 ✓）
                    //   这样算出来的路会**离平台边远一点** ✓ 而不是"最短但擦着边走" ✗
                    int risky = 0;
                    for (int[] e : ASTAR_DIRS4) {
                        if (!standable(lv, c.offset(e[0], 0, e[1]))) {
                            risky++;
                        }
                    }
                    cost += ASTAR_EDGE_PENALTY * risky / 4.0;
                    double ng = cg + cost;
                    if (ng < gScore.getOrDefault(c.asLong(), 1e9)) {
                        gScore.put(c.asLong(), ng);
                        came.put(c.asLong(), cur.asLong());
                        open.add(new AstarNode(c, ng + astarH(c, goal)));
                    }
                    // ★★v2.21（§79.366）✗★★：★**跳跃跨沟** ✗ 同层隔 1～2 格直线跳过去✗★ ✓
                    //   ★条件✗★：★中间那几格**脚层＋头层都要空**（★跳得过去✗★）✗
                    //            ★落点要 `standableOrDoor`（★站得住 ✗ 或门✗★）✗★ ✓
                    if (dy == 0 && d[0] != 0 ^ d[1] != 0) {
                        for (int gap = 2; gap <= 3; gap++) {
                            BlockPos t2 = cur.offset(d[0] * gap, 0, d[1] * gap);
                            if (t2.getX() < bx0 || t2.getX() > bx1
                                    || t2.getZ() < bz0 || t2.getZ() > bz1) {
                                continue;
                            }
                            if (!standableOrDoor(lv, t2)) {
                                continue;
                            }
                            boolean clear = true;
                            for (int s = 1; s < gap; s++) {
                                if (!passable2(lv, cur.offset(d[0] * s, 0, d[1] * s))
                                        || !passable2(lv, cur.offset(d[0] * s, 1, d[1] * s))) {
                                    clear = false;
                                    break;
                                }
                            }
                            if (!clear) {
                                continue;
                            }
                            double cost2 = 1.0 + 1.0 * gap;      // ★跳比走贵✗★
                            if (closedDoorAt(lv, t2) || closedDoorAt(lv, t2.above())) {
                                cost2 += 2.0;
                            }
                            double ng2 = cg + cost2;
                            if (ng2 < gScore.getOrDefault(t2.asLong(), 1e9)) {
                                gScore.put(t2.asLong(), ng2);
                                came.put(t2.asLong(), cur.asLong());
                                open.add(new AstarNode(t2, ng2 + astarH(t2, goal)));
                            }
                        }
                    }
                }
            }
        }
        BlockPos end = (found != null) ? found : best;
        java.util.LinkedList<BlockPos> out = new java.util.LinkedList<>();
        BlockPos walk = end;
        while (walk != null && !walk.equals(start)) {
            out.addFirst(walk);
            Long pk = came.get(walk.asLong());
            walk = (pk == null) ? null : BlockPos.of(pk);
        }
        return out;
    }

    /** ★重规划★ ✓（卡住 / 走完 / 人在半空 ⇒ 都来这儿 ✓）—— 顺手把"能不能到"记在任务上 ✗ */
    private static void replanWalk(ServerPlayer p, ServerLevel level, WalkTask t) {
        BlockPos from = BlockPos.containing(p.getX(), p.getY(), p.getZ());
        BlockPos goal = BlockPos.containing(t.tx, t.ty, t.tz);
        java.util.List<BlockPos> path = astarPath(level, from, goal);
        t.replans++;
        t.pathIdx = 0;
        t.path = path;
        t.nearest = null;
        if (path == null || path.isEmpty()) {
            t.goalReachable = false;
            t.nearest = from;
            return;
        }
        BlockPos last = path.get(path.size() - 1);
        t.goalReachable = last.equals(goal);
        t.nearest = t.goalReachable ? null : last;
    }

    private static int walkStart(CommandContext<CommandSourceStack> ctx, int ms, boolean exact)
            throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        ServerPlayer p = src.getPlayerOrException();
        BlockPos pos = BlockPosArgument.getLoadedBlockPos(ctx, "pos");
        ServerLevel level = lvl(p);
        long now = level.getGameTime();
        WalkTask t = new WalkTask(pos.getX(), pos.getY(), pos.getZ(),
                now + Math.max(10, ms / 50), exact, p.getX(), p.getZ(), now);
        WALKS.put(p.getUUID(), t);
        // ★v2.9：**开工前先算路** ✗ —— 顺手就把"目标到底能不能到"定下来 ✓
        //   ⇒ 这样智能体**一开始**就知道死活 ✗（而不是走一半才听一句含义模糊的 blocked ✓）
        replanWalk(p, level, t);
        ev("walk_start", "to=" + pos.toShortString() + " exact=" + exact + " ms=" + ms
                + " from=" + String.format("%.2f,%.2f,%.2f", p.getX(), p.getY(), p.getZ())
                + " path=" + (t.path == null ? 0 : t.path.size())
                + " reachable=" + t.goalReachable
                + " nearest=" + (t.nearest == null ? "-" : t.nearest.toShortString()));
        ok(src, "dshwalk start to=" + pos.toShortString() + " exact=" + exact + " budget_ms=" + ms
                + " from=" + String.format("%.2f,%.2f,%.2f", p.getX(), p.getY(), p.getZ())
                + " path=" + (t.path == null ? 0 : t.path.size())
                + " reachable=" + t.goalReachable
                + " nearest=" + (t.nearest == null ? "-" : t.nearest.toShortString()));
        return 1;
    }

    private static int walkStatus(CommandContext<CommandSourceStack> ctx) throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        ServerPlayer p = src.getPlayerOrException();
        ServerLevel level = lvl(p);
        WalkTask t = WALKS.get(p.getUUID());
        if (t == null) {
            ok(src, "dshwalk status=none (no active or recent walk)");
            return 0;
        }
        double d = Math.hypot(t.tx + 0.5 - p.getX(), t.tz + 0.5 - p.getZ());
        long ticks = t.startTick > 0 ? (level.getGameTime() - t.startTick) : -1;
        ok(src, "dshwalk status=" + (t.done ? "done" : "running")
                + " target=" + (int) t.tx + "," + (int) t.ty + "," + (int) t.tz
                + " at=" + String.format("%.2f,%.2f,%.2f", p.getX(), p.getY(), p.getZ())
                + " dist=" + String.format("%.2f", d)
                + " mode=" + (t.mode == 2 ? "manual" : t.mode == 1 ? "input" : "auto")
                + " result=" + (t.how.isEmpty() ? "-" : t.how)
                + " ticks=" + ticks + " detours=" + t.detours + " step_downs=" + t.stepDowns
                + " sprint=" + t.sprint
                + " path=" + (t.path == null ? "0" : t.pathIdx + "/" + t.path.size())
                + " replans=" + t.replans
                + " reachable=" + t.goalReachable
                + " next=" + ((t.path != null && t.pathIdx < t.path.size())
                        ? t.path.get(t.pathIdx).toShortString()
                        : ((t.nearest != null) ? "nearest:" + t.nearest.toShortString() : "-"))
                + " in_water=" + t.inWater
                + " why=" + (t.why.isEmpty() ? "none" : t.why));
        return t.done ? 2 : 1;
    }

    private static int walkStop(CommandContext<CommandSourceStack> ctx) throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        ServerPlayer p = src.getPlayerOrException();
        WalkTask t = WALKS.get(p.getUUID());
        if (t == null) {
            ok(src, "dshwalk stop: nothing to stop");
            return 0;
        }
        finish(p, t, "stopped_by_agent", lvl(p));
        ok(src, "dshwalk stop at=" + String.format("%.2f,%.2f,%.2f", p.getX(), p.getY(), p.getZ()));
        return 1;
    }

    /** ★逐 tick 走一步★ —— 这就是"像真人按住 W" ✓ 也是"一条指令走一整段"的落点 ✓ */

    // ★★v2.22（§79.386）✗★ 找一件**能垫脚的方块**（★抄 mineflayer `scafoldingBlocks`✗★）✗★
    private static int findScaffoldSlot(ServerPlayer p) {
        for (int i = 0; i < 36; i++) {
            net.minecraft.world.item.ItemStack st = p.getInventory().getItem(i);
            if (st.isEmpty()) {
                continue;
            }
            String id = net.minecraftforge.registries.ForgeRegistries.ITEMS.getKey(st.getItem()) == null ? ""
                    : net.minecraftforge.registries.ForgeRegistries.ITEMS.getKey(st.getItem()).getPath();
            if (id.contains("cobblestone") || id.contains("dirt") || id.equals("stone")
                    || id.contains("planks") || id.equals("sand") || id.equals("gravel")
                    || id.contains("deepslate") || id.equals("andesite") || id.equals("diorite")
                    || id.equals("granite") || id.equals("tuff") || id.equals("netherrack")) {
                return i;
            }
        }
        return -1;
    }

    // ★★v2.22（§79.386）✗★★ 1by1tower 一步：★在空中时把方块垫到自己**脚所在格**✗★★ ✓
    private static boolean pillarPlace(ServerPlayer p, ServerLevel lv, BlockPos feet) {
        if (!lv.getBlockState(feet).isAir()) {
            return false;
        }
        int slot = findScaffoldSlot(p);
        if (slot < 0) {
            return false;
        }
        p.getInventory().selected = slot < 9 ? slot : 0;
        if (slot >= 9) {
            return false;                     // ★不在快捷栏 ⇒ 不折腾（★保守✗★）✗★
        }
        net.minecraft.world.item.ItemStack st = p.getInventory().getItem(slot);
        try {
            p.gameMode.useItemOn(p, lv, st, net.minecraft.world.InteractionHand.MAIN_HAND,
                    new net.minecraft.world.phys.BlockHitResult(
                            net.minecraft.world.phys.Vec3.atCenterOf(feet.above()),
                            net.minecraft.core.Direction.DOWN, feet.above(), false));
            return true;
        } catch (Exception e) {
            return false;
        }
    }

    private static void tickWalk(ServerPlayer p) {
        WalkTask t = WALKS.get(p.getUUID());
        if (t == null) {
            return;
        }
        ServerLevel level = lvl(p);
        long now = level.getGameTime();
        if (t.done) {
            if (now - t.doneTick > 600) {          // 结果留 30 秒 ✓ 够智能体轮询 ✓
                WALKS.remove(p.getUUID());
            }
            return;
        }
        // ★v2.9：先保证有一条路 ✓（没有 / 走完 / 卡住 ⇒ 重规划 ✓
        //   —— 人在半空时 `standable(自己)` 是 false ✗ ⇒ A* 会自动从"最近能站的格"起步 ✓
        //      ＝ **自己落回去** ✓ 这就是原来那条"把悬空当 blocked"✗ 的解药 ✓）
        if (t.fixedRoute) {
            // ★★v2.23✗★ 路点表：★走完就收工 ✗ 不重规划（★PC 侧已规划好✗★）✗★
            if (t.path == null || t.pathIdx >= t.path.size()) {
                finish(p, t, "reached", level);
                return;
            }
        } else if (t.path == null || t.pathIdx >= t.path.size() || t.stuck > 20) {
            replanWalk(p, level, t);
            t.stuck = 0;
        }
        double dx = t.tx + 0.5 - p.getX();
        double dz = t.tz + 0.5 - p.getZ();
        double dist = Math.hypot(dx, dz);
        double stop = t.exact ? 0.7 : 1.0;
        // ★★v2.17：到达判据改成「**按格按层**」★★ ✗（交接 §61.5 第 2 条 ✓）
        //   旧判据 ✗：`dist <= stop && |dy| <= 1.3` 而 `dist` **只算水平** ✗
        //     ⇒ 「站在**旁边那一格**、而且**低一层**」也被算成"到了"✗
        //     —— 第 32 轮实测抓到过（§54.2 ✓ 目标 `(4121,72,5)`、实际停在 `(4120.30,71.00,4.46)` ✓）
        //   ★"假到"比"假没到"更贵✗★：大脑拿到"到了"就**接着动手**（开箱/挖/放）⇒ 那一下必然落空 ✗
        //   口径 ✓ 与中间层 `mc_mcp._walk` **逐字一致** ✗（P106 一处口径 ✓ 源码 `mc_mcp.py:182-184` ✓）：
        //     · 格：`floor(x)` ＋ `floor(z)` 对得上 ✓（`blockPosition()` 就是 floor ✓）
        //     · 层：`round(y)` 对得上 ✓ —— ★用 `Math.rint`✗★：它是**四舍六入五取偶** ✓
        //       ＝ Python 的 `round()` ✓（`Math.round` 是五**入** ✗ 在 `x.5` 上会与中间层**分家**✗）
        BlockPos cur = p.blockPosition();
        boolean sameCol = cur.getX() == (int) Math.floor(t.tx)
                && cur.getZ() == (int) Math.floor(t.tz);
        boolean sameLevel = (long) Math.rint(p.getY()) == (long) Math.floor(t.ty);
        if (sameCol && sameLevel) {
            finish(p, t, "reached", level);
            return;
        }
        if (now > t.endTick) {
            t.why = "budget exhausted (moved " + String.format("%.2f", Math.hypot(p.getX() - t.lastX, p.getZ() - t.lastZ)) + " in last tick window)";
            finish(p, t, "timeout", level);
            return;
        }
        // ★疾跑：路还长（>4 格）时就跑起来 ✓（真人远路会跑 ✓ 实测速度要一起报出来 ✗ 别只说"变快了"✗）
        // sec 79.458: sprint is a STATE, not a per-tick condition. p.onGround() is
            //   false for the whole airborne part of a jump, so sprint flickered
            //   off every jump (measured 38/107 ticks). Vanilla keeps sprinting
            //   mid-air if the jump started while sprinting.
            t.sprint = dist > 4.0;
        // ★★§79.436✗★ 每 tick：★位移／疾跑／视角变化✗★
        if (!Double.isNaN(t.statPX)) {
            double _dx = p.getX() - t.statPX, _dz = p.getZ() - t.statPZ;
            t.dist += Math.sqrt(_dx * _dx + _dz * _dz);
            t.motionTicks++;
            if (Math.abs(p.getYRot() - t.statYaw) > 1.0f) {
                t.lookChanges++;
            }
        }
        t.statPX = p.getX();
        t.statPZ = p.getZ();
        t.statYaw = p.getYRot();
        if (t.sprint) {
            t.sprintTicks++;
        }
        // ★★§79.440✗★★：★"★真的跳了★"看 **y 真的升上去** ✗ 不看"★我有没有把 vy 设成 0.42★"✗★
        //   ★为什么✗★：★台阶可能靠**自动跳／垫脚**上去 ✗ 那也算跳 ✗ 老判据漏了（★2.37.0 实测 jumps=0✗★）
        if (!Double.isNaN(t.statPY) && p.getY() - t.statPY > 0.30) {
            t.jumps++;
        }
        t.statPY = p.getY();
        lastMoveStats = t.moveStats();
        try {
            p.setSprinting(t.sprint);
        } catch (Exception ignored) {
            // 设不了就算了 ✓ —— 但**速度会如实反映在基准里** ✓（不假装跑起来了 ✗）
        }
        // ① 朝向目标 ✓（★顺带就是"头随路转"✓ 最便宜的一处人感 ✓）
        //   ⚠ v2.7：**只在偏差大时才重新瞄准** ✗ —— 每 tick 都 aimAt 会让它一直小幅摆头 ✗
        //     （真人不会每 50ms 修一次朝向 ✓ 而且来回摆动会**吃掉前进速度** ✗）
        // ★v2.9：瞄**路径的下一格** ✗ 而不是"终点" ✓（一条真路 ＋ 原来的移动/跳跃/边界那套原样保留 ✓）
        BlockPos aim = (t.path != null && t.pathIdx < t.path.size()) ? t.path.get(t.pathIdx) : null;
        double aimX = (aim != null) ? aim.getX() + 0.5 : t.tx + 0.5;
        double aimZ = (aim != null) ? aim.getZ() + 0.5 : t.tz + 0.5;
        if (aim != null && Math.hypot(aimX - p.getX(), aimZ - p.getZ()) <= 0.7
                && Math.abs(aim.getY() - p.getY()) <= 1.2) {
            t.pathIdx++;                              // 到跟前了 ⇒ 推进下一格 ✓
            aim = (t.pathIdx < t.path.size()) ? t.path.get(t.pathIdx) : null;
            aimX = (aim != null) ? aim.getX() + 0.5 : t.tx + 0.5;
            aimZ = (aim != null) ? aim.getZ() + 0.5 : t.tz + 0.5;
        }
        // ★★v2.20（§79.363）✗★ 下一格是门 ⇒ **先开** ✗★
        tryOpenDoor(p, level, aim);
        double wantYaw = yawTo(p, aimX, p.getEyeY(), aimZ);
        double dYaw = Math.abs(normDeg(wantYaw - p.getYRot()));
        if (dYaw > 12.0) {
            aimAt(p, new Vec3(aimX, p.getEyeY(), aimZ));
        }
        double rad = Math.toRadians(p.getYRot());
        double fx = -Math.sin(rad), fz = Math.cos(rad);     // 与 aimAt 的 yaw 约定一致 ✓
        // ② ★空岛安全：前方没有落脚点就**停手**★ ✗（宁可不动 ✓ 也不掉虚空 ✓）
        //   ★★v2.7 修了一个真错误★★ ✗：v2.6 用 `p.getY() - 0.2` 取样 ✗
        //     ⇒ 取到的是**脚下那一层**（y=70）✗ 于是检查的是 y=69 / y=68 ✗
        //     而空岛地板**只有 1 格厚** ✗ ⇒ 恒为"没有支撑"✗ ⇒ **一路上到处误停** ✗
        //     （实测：`why=edge ahead: no support at 4113,69,5` ✗ 而它脚下明明是实心的 ✓）
        //   ⇒ v2.7 起按**脚所在的那一层**取样 ✓：脚在 y ⇒ 同层地板 = `below()` ✓
        //     ⚠ **v2.17 起这一段被下面"逐层找第一个实心面"取代** ✗★ ——
        //       「再下一层 `below(2)` 有东西 ⇒ 那是 1 格台阶」这句**只认降 1 格** ✗，
        //       正是 **P140** 的根因 ✗ ⇒ 现在落差口径与 A* 的 `MAX_DROP` **统一** ✓ 见下 ✓
        BlockPos nb = BlockPos.containing(p.getX() + fx * 1.0, p.getY(), p.getZ() + fz * 1.0);
        // ★★v2.17：落差口径与 A* **统一**★★ ✗（P140 的真根因 ✓ 这一段以前**只认降 1 格** ✗）
        //   旧行为 ✗：`below()` / `below(2)` 都没有 ⇒ 判"没有落脚点" ⇒ `finish(..., "edge")` ✗
        //     ⇒ **一步降 2 格被当成虚空** ✗ ⇒ 安全规则把人**关在桶顶上** ✗（P124 一族 ✓）
        //   现在 ✓：逐层往下找**第一个实心面** ⇒ 落差 <= `MAX_DROP` 且下落通道全通 ⇒ **放行** ✓
        int drop = landingDrop(level, nb, MAX_DROP + 1);
        // ★★v2.18.1 修：这条闸**不许**把"正前方那一格被占"当成 `edge`✗★★
        //   （2026-10-01 **实测抓到的回归** ✓ —— 修的是我自己在 v2.17 加的东西 ✓）
        //
        //   现场 ✗（事件流原文 ✓，是 `walk_refuse` 那条新事件把它照出来的 ✓ 见 P138 ✓）：
        //     假人站在一堆家具/机器中间（21×21 内 `blocked=64` ✓），
        //     正前方那格被 `mcwfurnitures:mangrove_stool_chair` 占着 @ `(4118,71,8)` ✓ ⇒
        //     ```
        //     #3 walk_refuse kind=edge why=step_down=0 > max_drop=3 at=4118, 71, 8
        //     #4 walk_done  result=edge ... 位移 0.00
        //     ```
        //     ⇒ ★`step_down=0 > max_drop=3` 是句**废话**✗★（0 **不大于** 3 ✓）
        //     ⇒ 更要命的 ✗：它当场 `finish(edge)` ⇒ ★再也走不到 v2.16 那套
        //       "撞上 ⇒ 没进展 ⇒ 重规划 ⇒ 绕障"✗★ ⇒ 在**杂物区硬拒、位移 0** ✗
        //
        //   根因 ✓（**我自己的错** ✗）：v2.17 加"下落通道要通"时，
        //     ★把手搓的 `nb` 自己也塞进了通道检查 ✗★ ——
        //     而 `nb` 被占 ＝ **"被挡住"** ✓ 那是**移动层**的事 ✗ **不是"落差/虚空"**的事 ✓
        //
        //   ★口径 ✓（**P106**：一个谓词只许一个含义 ✗）★：
        //     · 这条闸**只管落差** ✓：找不到地板 ⇒ **真虚空** ✓；落差 > `MAX_DROP` ⇒ **太深** ✓
        //     · "正前方被挡" 一律**交给下面既有的** `noProgress` ⇒ 重规划 ⇒ 绕障 那一套 ✓
        //   ⚠ 顺带说清 ✓：`drop >= 1` 时**落地那格必然是空的** ✗ ——
        //     因为 `landingDrop` 找的是**第一个实心面** ✓ ⇒ 它上面 `1..drop-1` 层**都非实心** ✓
        //     ⇒ ★"下落通道通"这条**由构造自动成立**✗★ ⇒ 不必（也不该）再查一遍 ✓
        boolean canStep = drop >= 0 && drop <= MAX_DROP;
        if (p.onGround() && !canStep) {
            // ★v2.17：P124 纪律① —— 拦之前**先问"我现在出不出去"**✗★
            //   ⇒ 出不去 ⇒ 这是**牢笼** ⇒ **不许拦** ✓（宁可让它走这一步 ✗ 也不把它关起来 ✓）
            //   ⇒ 放宽上限 `MAX_DROP_HARD` ⇒ ★绝不走进真虚空✗★（找不到地板就照拦 ✓）
            int deep = landingDrop(level, nb, MAX_DROP_HARD + 1);
            if (deep >= 0 && lockedIn(level, p)) {
                ev("walk_relaxed", "reason=locked_in step_down=" + deep
                        + " max_drop=" + MAX_DROP + " at=" + nb.toShortString());
                drop = deep;
                canStep = true;
            } else {
                // ★v2.17：`why` 用词改清楚 ✗★（P140 §5.3 ✓）
                //   旧词 `edge ahead: no support ...` 里的 **no support 听起来像"虚空"**✗
                //   而实际常常是"**落差有 N 格**" ✗ ⇒ 连 `walk_diag.py` 的归类都被它带偏了 ✗
                //   ⇒ 改成**写明数字** ✓（几格就写几格 ✓ 真虚空才写 `void` ✓）
                t.why = "step_down=" + (drop < 0 ? "void" : String.valueOf(drop))
                        + " > max_drop=" + MAX_DROP + " at=" + nb.toShortString();
                // ★v2.17：拒绝必须**同时**发一条 ASCII 事件 ✗★（P138 纪律 ✓）
                //   走 CC 通道的回执**读不出中文**✗（全变 `?` ✗）⇒ 不补事件 ⇒ 下次诊断还是卡死 ✗
                //   ⚠ 新事件名 ⇒ ★必须在 `tools/speech.py` 的 `EVENT_KINDS`/`SKIP_EVENTS` 里做个决定✗★
                //     （不然 `errata_guard_test.py` 的 **E11** 双向对账会报红 ✓ —— 它正是为此存在的 ✓）
                ev("walk_refuse", "kind=edge why=" + t.why);
                finish(p, t, "edge", level);
                return;
            }
        }
        if (canStep && drop >= 1) {
            t.stepDowns++;                       // ★降几格都如实记账 ✓（别只记"1 格台阶"✗）
        }
        // ③ 要跳吗？（前方 1 格挡路 ＋ 头顶是空的 ⇒ 真人也是跳一下 ✓）
        BlockPos aheadFeet = BlockPos.containing(p.getX() + fx * 0.6, p.getY(), p.getZ() + fz * 0.6);
        boolean blocked = solidAt(level, aheadFeet);
        boolean headroom = !solidAt(level, aheadFeet.above());
        // ★★§79.419✗★★：★**绕障时也要能跳**✗ —— 旧条件 `t.detourTicks == 0` 让
        //   ★一进绕障就**永远不跳** ⇒ 顶在**1 格台阶**前卡死✗★（★2.31.0 实测：
        //   `walk_timeout@4120,72,17` ✗ 目标只是**正交上 1 格**✗★）✗★ ✓
        // ★★§79.429✗★★：★`wantJump` 原来只看"前方**有方块挡路**"✗
        //   ★⇒ ★**1 格沟**（前方空气 ✗ 再前面才是地）**不跳** ⇒ 掉一格走下去（★不像人 ✗ 还慢✗★）✗★
        //   ★加✗★：★前方**没支撑** ∧ **两格外有支撑** ⇒ **跳**（★真人跨沟就是这样✗★）✗★ ✓
        boolean gapAhead = false;
        if (!blocked && p.onGround()) {
            BlockPos a1 = BlockPos.containing(p.getX() + fx * 0.9, p.getY() - 1, p.getZ() + fz * 0.9);
            BlockPos a2 = BlockPos.containing(p.getX() + fx * 1.9, p.getY() - 1, p.getZ() + fz * 1.9);
            boolean noSupportAhead = !solidAt(level, a1);
            boolean supportAfter = solidAt(level, a2);
            boolean headroom2 = !solidAt(level, a1.above()) && !solidAt(level, a2.above());
            gapAhead = noSupportAhead && supportAfter && headroom2;
        }
        // ★★§79.442✗★ 动作类型参与判定：★规划说"跳"就跳 ✗ 说"落"就不跳✗★
        boolean wantJump = (blocked || gapAhead || t.forceJump) && headroom && p.onGround()
                && !t.forceNoJump;
        // ★★v2.22（§79.386）✗★ 1by1tower：★下一格高自己 1 格 ✗ 脚格是空气 ✗ 有垫脚方块★ ⇒ 跳＋垫✗★
        if (WalkTask.ALLOW_PILLAR
                && t.pillarTicks == 0 && p.onGround() && aim != null
                && aim.getY() == p.blockPosition().getY() + 1
                && level.getBlockState(p.blockPosition()).isAir()
                && findScaffoldSlot(p) >= 0) {
            t.pillarTicks = 10;
            ev("walk_pillar", "start aim=" + aim.toShortString());
        }
        // ★★v2.21（§79.366）✗★★：★下一格**隔空**（>1.6 格）⇒ 得跳过去 ✗★
        //   ★原来只在前方被挡时才跳 ✗ 所以"跳沟"永远不触发✗★ ✓
        if (!wantJump && t.detourTicks == 0 && p.onGround() && aim != null
                && Math.hypot(aimX - p.getX(), aimZ - p.getZ()) > 1.6) {
            wantJump = true;
        }
        // ④ ★绕障（v2.7 新增）★ ✗：直走被挡太久就**沿墙侧走一段** ✓ 然后回到直线 ✓
        //   为什么要它 ✗（有实测现场 ✓）：
        //     假人从农田去桶边 ✓ 直线撞上 `mcwfences` 那道墙（x=4114、z 7..11 ✗）
        //     —— 墙高 1.5 格 ⇒ **跳不过去** ✗（真人也不行 ✓）⇒ 真人会**绕**✓
        //     而 v2.6 只会"卡住 → 报 blocked"✗（同一列卡了 3 次 ✓ 与 P21 的 path_goto 卡在**同一个 x** ✓）
        //   ⇒ 所以：侧向走一小段 ✓ 再试直线 ✓ 绕不过去就**如实报**✗（有次数上限 ✓ 不许无限转圈 ✗）
        double sideSign = 1.0;
        boolean backOff = false;
        if (t.detourTicks > 0) {
            t.detourTicks--;
            sideSign = t.detourDir > 0 ? 1.0 : -1.0;
            backOff = Math.abs(t.detourDir) == 2;      // ★先退再绕★ ✓（贴墙时的正解 ✓）
        }
        // ⑤ 推进 ✓ —— ★两种驱动方式都实现 ✓ 由**实测**决定用哪个 ✗（不猜 ✓）
        // ★★v2.13：会游泳★★ ✗（用户实测：掉水里就在原地扑腾 / 不肯下水 ✓）
        //   为什么这样写 ✗：`p.yya` 就是"跳"这个**输入轴** ✓
        //   真人按住 W ＋ 空格在水里就会上浮 ✓ ⇒ 我们照做 ✓（不改驱动方式 ✓ 风险最小 ✓）
        //   ⚠ 在水里时**不走 manual 那套**（mode==2 ✓）—— 因为手推速度会把上浮抵消掉 ✗
        t.inWater = p.isInWater();
        if (t.inWater) {
            p.xxa = 0.0f;
            p.zza = 1.0f;                        // 朝目标前进 ✓（朝向已在上面瞄好 ✓）
            p.yya = 1.0f;                        // ＝按住跳 ⇒ 上浮 ✓
            try {
                p.setSprinting(false);           // 水里疾跑没意义 ✓ 而且会消耗饱食 ✓
            } catch (Exception ignored) {
            }
        } else if (t.mode != 2) {
            if (t.detourTicks > 0) {
                p.xxa = (float) (sideSign * 1.0);   // 侧向 = 真人按住 A/D 绕开 ✓
                p.zza = backOff ? -0.7f : 0.35f;    // 贴墙时**先退**✓ 否则带一点前进 ✓
            } else {
                p.xxa = 0.0f;
                p.zza = 1.0f;                       // ＝ 真人按住 W ✓
            }
            p.yya = 0.0f;
            // ★★v2.22（§79.386）✗★ pillar 执行：★地上就跳 ✗ 空中就垫✗★
            if (t.pillarTicks > 0) {
                t.pillarTicks--;
                if (p.onGround()) {
                    p.setDeltaMovement(p.getDeltaMovement().x, 0.42, p.getDeltaMovement().z);
                } else if (pillarPlace(p, level, p.blockPosition())) {
                    t.pillarPlaced++;
                    ev("walk_pillar", "placed=" + p.blockPosition().toShortString()
                            + " total=" + t.pillarPlaced);
                    t.pillarTicks = 0;
                }
            }
            if (wantJump) {
                p.setDeltaMovement(p.getDeltaMovement().x, 0.42, p.getDeltaMovement().z);
            }
        } else {
            double speed = t.sprint ? 0.216 : 0.13; // ≈ 真人步行 4.3 m/s；疾跑 5.6 m/s ✓
            double mx = fx, mz = fz;
            if (t.detourTicks > 0) {                // 侧向 = 把前进方向转 90° ✓
                mx = -fz * sideSign - (backOff ? fx * 0.7 : 0);
                mz = fx * sideSign - (backOff ? fz * 0.7 : 0);
            }
            if (wantJump && p.onGround()) {
            t.jumps++;                       // ★★§79.436✗★ 真的起跳 ✗ 记一笔✗★
        }
        double vy = p.onGround() ? (wantJump ? 0.42 : 0.0) : p.getDeltaMovement().y - 0.08;
            Vec3 want = new Vec3(mx * speed, vy, mz * speed);
            p.setDeltaMovement(want);
            p.move(net.minecraft.world.entity.MoverType.SELF, want);
        }
        // ★v2.9：路走完了却还没到 ⇒ **如实报"目标不可达"** ✗（带上最近能到的那个可站格 ✓）
        if (!t.goalReachable && t.path != null && t.pathIdx >= t.path.size() && dist > stop + 0.3) {
            t.why = "target unreachable: nearest standable is "
                    + (t.nearest == null ? "?" : t.nearest.toShortString())
                    + " dist=" + String.format("%.2f", dist);
            finish(p, t, "unreachable", level);
            return;
        }
        // ⑥ 进度 / 卡住诊断 ＋ **绕障触发** ✓（★P21 缺的就是那句"为什么"✗）
        double moved = Math.hypot(p.getX() - t.lastX, p.getZ() - t.lastZ);
        if (moved < 0.02) {
            t.noProgress++;
            t.stuck++;
            if (t.noProgress > 12 && t.mode != 2) {
                t.mode = 2;
                t.noProgress = 0;
                ev("walk_mode", "manual (vanilla input did not move the player)");
            } else if (t.noProgress > 20 && t.detourTicks == 0 && t.detours < 40) {
                // ★挑一侧绕开 ✗：**第一次**挑完就**记住** ✓（"认准一边走到底" ✓ —— v2.8.1 ✓）
                //   为什么不能每次重挑 ✗：实测它会**左右横跳** ⇒ 侧步全抵消 ⇒ 原地打转 ✗✗
                // ★v2.9：**先重规划** ✗ —— 贴墙侧移是下策 ✓（那条路是"没有地图时"的将就办法 ✓）
                //   重规划有上限（15 次 ✓）⇒ 用完了再退回老的绕障 ⇐ 环路也堵住了 ✗
                if (t.replans < 15) {
                    replanWalk(p, level, t);
                    t.noProgress = 0;
                    t.stuck = 0;
                    ev("walk_replan", "n=" + t.replans + " path="
                            + (t.path == null ? 0 : t.path.size())
                            + " reachable=" + t.goalReachable);
                } else {
                int dir = t.detourSide != 0 ? t.detourSide : pickDetour(p, level, fx, fz);
                if (dir != 0) {
                    t.detourSide = dir;
                    t.detours++;
                    t.detourDir = dir;
                    t.detourTicks = 20;             // ≈1 秒 ✓ 比 v2.7.1 的 14 长一点 ✓（一次多挪一点 ✓）
                    t.freeTicks = 0;
                    t.noProgress = 0;
                    ev("walk_detour", "n=" + t.detours + " side=" + (dir > 0 ? "left" : "right")
                            + (Math.abs(dir) == 2 ? " backoff" : "")
                            + " locked=" + t.detourSide
                            + " at=" + String.format("%.2f,%.2f,%.2f", p.getX(), p.getY(), p.getZ())
                            + " blocked=" + aheadFeet.toShortString());
                } else {
                    t.why = "blocked and no side is walkable: aheadBlocked=" + blocked
                            + " headroom=" + headroom + " onGround=" + p.onGround()
                            + " drop=" + drop
                            + " mode=" + (t.mode == 2 ? "manual" : "input");
                    // ★v2.17：拒绝就**同时**发一条 ASCII 事件 ✗★（P138 纪律 ✓）
                    //   （回执走 CC 通道**读不出中文**✗ ⇒ 只靠回执 ⇒ 下次诊断还是卡死 ✗）
                    ev("walk_refuse", "kind=blocked why=" + t.why);
                    finish(p, t, "blocked", level);
                    return;
                }
                }                                  // ← 收住上面的 "else（退回老绕障）" ✓
            } else if (t.noProgress > 80) {
                t.why = "blocked: no movement for 80 ticks; aheadBlocked=" + blocked
                        + " headroom=" + headroom + " onGround=" + p.onGround()
                        + " drop=" + drop + " detours=" + t.detours
                        + " mode=" + (t.mode == 2 ? "manual" : "input");
                ev("walk_refuse", "kind=blocked why=" + t.why);   // ★v2.17：同上 ✓
                finish(p, t, "blocked", level);
                return;
            }
        } else {
            t.stuck = 0;
            if (t.mode == 0) {
                t.mode = 1;                     // 记下"原版输入法**真的**能走"✓（下一版就能省掉另一套 ✓）
                ev("walk_mode", "input (vanilla xxa/zza works)");
            }
            t.noProgress = 0;
            // ★"走得动"够久了 ⇒ **解锁绕障方向** ✓（否则绕完墙还会一直贴着走 ✗）
            if (t.detourSide != 0 && ++t.freeTicks > 60) {
                ev("walk_detour", "unlock side (free for 60 ticks)");
                t.detourSide = 0;
                t.freeTicks = 0;
            }
        }
        t.lastX = p.getX();
        t.lastZ = p.getZ();
    }

    /** 目标方位的 yaw ✓（与 `aimAt` 同一套约定 ✓ 但**不改朝向**✗ ⇒ 用来判断"偏了多少"✓） */
    private static float yawTo(ServerPlayer p, double x, double y, double z) {
        Vec3 eye = p.getEyePosition();
        double dx = x - eye.x, dy = y - eye.y, dz = z - eye.z;
        double horiz = Math.sqrt(dx * dx + dz * dz);
        return (float) (Math.toDegrees(Math.atan2(-dx, dz)));
    }

    /** 把角度归一化到 [-180,180] ✓（不然 179° 与 -179° 之差会算成 358° ✗） */
    private static double normDeg(double d) {
        while (d > 180.0) d -= 360.0;
        while (d < -180.0) d += 360.0;
        return d;
    }

    /** 左/右哪一侧能走 ✓ → 编码如下（**含"先退一步再绕"** ✗ 这一手是实测补的 ✓）：
     * <pre>
     *   +1 = 就地往左   -1 = 就地往右
     *   +2 = 先退再往左 -2 = 先退再往右
     *    0 = 两边都不行 ⇒ 调用方**如实报 blocked**✗（不硬闯 ✓）
     * </pre>
     *
     * <p>★为什么必须加"先退一步"✗★（2026-09-19 深夜实测 ✓ 教训很具体 ✓）：
     * 假人顶着 `mcwfences` 那道墙走 ✓ 停在 **x=4114.07**（**贴**着墙 ✗ —— 墙柱的碰撞箱很窄 ✓
     * 所以它能挤到方块格**里面**去 ✓）⇒ 此时它左右两格**都是墙柱** ✗
     * ⇒ 我第一版只试"就地侧移"✗ ⇒ 判"两边都走不了"✗ 然后**如实报 blocked** ✓ ——
     * 报得没错 ✓ 但**没用** ✗：真人遇到这种情况是**先退半步、再沿墙挪** ✓
     * ⇒ 所以：就地不行就试"**退一格之后再侧移**"✓ 那一格通常就是它刚走过的空地 ✓
     */
    private static int pickDetour(ServerPlayer p, ServerLevel level, double fx, double fz) {
        for (int s : new int[]{1, -1}) {
            double sx = -fz * s, sz = fx * s;                  // 侧向单位向量 ✓
            if (walkableAt(p, level, p.getX() + sx, p.getZ() + sz)) {
                return s;
            }
        }
        for (int s : new int[]{1, -1}) {
            double sx = -fz * s, sz = fx * s;
            if (walkableAt(p, level, p.getX() - fx + sx, p.getZ() - fz + sz)) {
                return s * 2;                                  // 先退再侧移 ✓
            }
        }
        return 0;
    }

    /** 那一格"站得下人"吗 ✓（脚下有支撑 ✓ 身上两格是空的 ✓） */
    private static boolean walkableAt(ServerPlayer p, ServerLevel level, double x, double z) {
        BlockPos feet = BlockPos.containing(x, p.getY(), z);
        return solidAt(level, feet.below())
                && !solidAt(level, feet)
                && !solidAt(level, feet.above());
    }

    private static void finish(ServerPlayer p, WalkTask t, String how, ServerLevel level) {
        p.xxa = 0.0f;
        p.zza = 0.0f;
        p.yya = 0.0f;
        t.done = true;
        t.doneTick = level.getGameTime();
        t.atX = p.getX();
        t.atY = p.getY();
        t.atZ = p.getZ();
        t.how = how;
        double d = Math.hypot(t.tx + 0.5 - p.getX(), t.tz + 0.5 - p.getZ());
        long ticks = t.startTick > 0 ? (level.getGameTime() - t.startTick) : -1;
        double travelled = Math.hypot(p.getX() - t.fromX, p.getZ() - t.fromZ);
        String speed = (ticks > 0 && travelled > 0.5)
                ? String.format("%.2f bps (%.0f ticks, %.1f blocks walked)",
                        travelled / (ticks / 20.0), (double) ticks, travelled)
                : "n/a";
        ev("walk_done", "result=" + how
                + " at=" + String.format("%.2f,%.2f,%.2f", t.atX, t.atY, t.atZ)
                + " want=" + (int) t.tx + "," + (int) t.ty + "," + (int) t.tz
                + " dist=" + String.format("%.2f", d)
                + " mode=" + (t.mode == 2 ? "manual" : t.mode == 1 ? "input" : "auto")
                + " detours=" + t.detours + " step_downs=" + t.stepDowns
                + " known_speed=" + (speed.equals("n/a") ? "n/a" : speed.split(" ")[0])
                + (t.detourSide != 0 ? " detour_side=" + (t.detourSide > 0 ? "left" : "right") : "")
                + (t.sprint ? " sprint=yes" : "")
                + " pillar=" + t.pillarPlaced
                + (t.pillarPlaced > 0 ? " ★改了世界✗★" : "")
                + (t.why.isEmpty() ? "" : " why=" + t.why));
    }

    // ── /dshevents ────────────────────────────────────────────────────────────
    private static int events(CommandContext<CommandSourceStack> ctx, int since) {
        CommandSourceStack src = ctx.getSource();
        List<String> out = new ArrayList<>();
        synchronized (EVENTS) {
            for (String l : EVENTS) {
                int sp = l.indexOf(' ');
                int seq = Integer.parseInt(l.substring(1, sp));
                if (since >= 0 && seq <= since) {
                    continue;
                }
                out.add(l);
            }
        }
        int show = Math.min(out.size(), 40);
        StringBuilder sb = new StringBuilder("dshevents watched=" + WATCHED
                + " total=" + EVENT_SEQ.get() + " new=" + out.size() + " cursor=" + EVENT_SEQ.get());
        for (int i = Math.max(0, out.size() - show); i < out.size(); i++) {
            sb.append(" | ").append(out.get(i));
        }
        if (out.size() > show) {
            sb.append(" | (older ").append(out.size() - show).append(" not shown)");
        }
        ok(src, sb.toString());
        return out.size();
    }

    private static int eventsWatch(CommandContext<CommandSourceStack> ctx) {
        WATCHED = StringArgumentType.getString(ctx, "name");
        ok(ctx.getSource(), "dshevents watch name=" + WATCHED);
        return 1;
    }

    /** 低频观测 ✓（每 10 tick ✓ **便宜** ✓ 而且全是"值得记一笔"的事 ✓） */
    private static void tickWatch(ServerPlayer p) {
        String mode = p.isCreative() ? "creative" : p.isSpectator() ? "spectator" : "survival";
        double hp = p.getHealth();
        double food = p.getFoodData().getFoodLevel();
        int items = 0;
        for (int i = 0; i < 36; i++) {
            ItemStack s = p.getInventory().getItem(i);
            if (!s.isEmpty()) {
                items += s.getCount();
            }
        }
        ItemStack held = p.getMainHandItem();
        String heldId = held.isEmpty() ? "none" : idOf(held);
        if (!wMode.isEmpty() && !wMode.equals(mode)) {
            // ★P17 的警报★ ✓：世界重启后 spawn 出来是创造模式 ⇒ 挖掘不掉落 ⇒ 自给证据失真 ✗
            ev("mode", "from=" + wMode + " to=" + mode + (mode.equals("creative") ? " WARN_creative" : ""));
        }
        if (wHp >= 0 && hp < wHp - 0.01) {
            var ds = p.getLastDamageSource();
            ev("damage", String.format("hp=%.1f delta=%.1f src=%s", hp, hp - wHp,
                    ds == null ? "unknown" : ds.getMsgId()));
        }
        if (wFood >= 0 && food > wFood + 0.01) {
            ev("ate", "food=" + (int) food + " delta=+" + (int) (food - wFood) + " held=" + heldId);
        }
        if (wInv >= 0 && items != wInv) {
            ev("inv", "delta=" + (items - wInv) + " items=" + items + " held=" + heldId);
        }
        if (wSel >= 0 && p.getInventory().selected != wSel) {
            ev("hotbar", "sel=" + p.getInventory().selected + " held=" + heldId);
        }
        if (wXp >= 0 && p.experienceLevel != wXp) {
            ev("xp", "level=" + p.experienceLevel);
        }
        if (!wHeld.isEmpty() && !wHeld.equals(heldId)) {
            ev("held", "from=" + wHeld + " to=" + heldId);
        }
        // ★位置瞬移 = 有人 `tp` 它 ★ ✗（给"主线不走 tp"那条纪律当哨兵 ✓ 也给 P17 那种失真兜底 ✓）
        if (!Double.isNaN(wX)) {
            double jump = Math.hypot(p.getX() - wX, p.getZ() - wZ) + Math.abs(p.getY() - wY);
            if (jump > 8.0) {
                ev("warp", String.format("from=%.1f,%.1f,%.1f to=%.1f,%.1f,%.1f d=%.1f",
                        wX, wY, wZ, p.getX(), p.getY(), p.getZ(), jump));
            }
        }
        // ★v2.13.1：皮肤自愈 ✗（重生/重连/重启之后自己长回来 ✓）
        // ★v2.13.3：**先读状态文件再判断** ✗ —— 实测抓到：原来 load 放在 startSkinHttp 里 ✓
        //   而那边要等 SKIN_CHOSEN 非空才会被调用 ✗ ⇒ **鸡生蛋** ⇒ 状态文件永不读取 ✗
        //   （表现：skin_heal 一次没出现 ＋ skin_http.log 不存在 ✓ 见 logs/runbook.txt ✓）
        skinStateLoad();
        skinSelfHeal(lvl(p));
        // ★地上的掉落物 ＋ ★快消失的掉落物★ ✗（这就是 P20 那次丢 25 个绿宝石的警报 ✓）
        AABB box = p.getBoundingBox().inflate(8.0);
        for (Entity en : lvl(p).getEntities(p, box, x -> x instanceof ItemEntity)) {
            ItemEntity ie = (ItemEntity) en;
            int left = ie.lifespan - ie.getAge();
            if (left < 600 && wDropWarned.putIfAbsent(ie.getId(), left) == null) {
                ev("drop_expiring", "id=" + ie.getId() + " item=" + idOf(ie.getItem())
                        + " x" + ie.getItem().getCount() + " left_s=" + (left / 20)
                        + " at=" + String.format("%.1f,%.1f,%.1f", ie.getX(), ie.getY(), ie.getZ())
                        + " dist=" + String.format("%.1f", p.distanceTo(ie))
                        + " (pickup needs a FREE SLOT - see inv_guard)");
            }
        }
        wHp = hp; wFood = food; wInv = items; wSel = p.getInventory().selected;
        wXp = p.experienceLevel; wX = p.getX(); wY = p.getY(); wZ = p.getZ();
        wMode = mode; wHeld = heldId;
        if (wDropWarned.size() > 500) {          // 有界 ✓（实体 id 会复用 ✓ 但别让它无限涨 ✗）
            wDropWarned.clear();
        }
    }

    // ── /dshauto ──────────────────────────────────────────────────────────────
    private static int autoStatus(CommandContext<CommandSourceStack> ctx) {
        ok(ctx.getSource(), "dshauto eat=" + AUTO_EAT + " minfood=" + AUTO_EAT_MIN
                + " idle=" + AUTO_IDLE + " (idle defaults OFF: it would rotate the crosshair"
                + " away from a running sift - see P16)");
        return 1;
    }

    private static int autoEat(CommandContext<CommandSourceStack> ctx, boolean on, int min) {
        AUTO_EAT = on;
        AUTO_EAT_MIN = min;
        ok(ctx.getSource(), "dshauto eat=" + on + " minfood=" + min);
        return 1;
    }

    private static int autoIdle(CommandContext<CommandSourceStack> ctx, boolean on) {
        AUTO_IDLE = on;
        ok(ctx.getSource(), "dshauto idle=" + on
                + (on ? " (WARNING: do not enable while a long crosshair-dependent job runs)" : ""));
        return 1;
    }

    /** 自动行为：只在**该动**的时候动 ✓（吃东西 ✓ 空闲看四周 ✓ 自己溜达 ✓ 跟人打招呼 ✓） */
    private static void tickAuto(ServerPlayer p) {
        if (!p.getName().getString().equals(WATCHED)) {
            return;
        }
        ServerLevel level = lvl(p);
        long now = level.getGameTime();
        if (AUTO_EAT && !p.isUsingItem() && p.getFoodData().getFoodLevel() < AUTO_EAT_MIN
                && p.onGround() && p.getVehicle() == null) {
            autoEatTick(p);
        }
        if (AUTO_IDLE && !WALKS.containsKey(p.getUUID())
                && now - LAST_CMD_TICK > 120            // 6 秒内有过指令 ⇒ 一定不是空闲 ✓
                && p.onGround() && !p.isUsingItem()
                && p.getDeltaMovement().horizontalDistanceSqr() < 1.0E-4
                && now % 60 == 0) {
            glance(p);
            nGlance++;
            lastGlanceTick = now;
        }
        // ══ ★★v2.8：拟人化（用户点名的两条 ✓）★★ ═══════════════════════════════
        if (!HUMANOID || WALKS.containsKey(p.getUUID()) || p.isUsingItem() || !p.onGround()) {
            return;                                     // 正在走路/吃东西/腾空 ⇒ **一律不动** ✗
        }
        if (Double.isNaN(anchorX)) {                    // 第一 tick：把脚下这一片当"家" ✓
            anchorX = p.getX();
            anchorY = p.getY();
            anchorZ = p.getZ();
        }
        if (!isQuiet(now)) {
            return;                                     // ★总门槛★ ✗ 有人在指挥它 ⇒ 不许自作主张 ✓
        }
        // ① 玩家走近 ⇒ 打招呼 ✓（同一个玩家 60 秒内只打一次 ✓ 绝不刷屏 ✗）
        AABB near = p.getBoundingBox().inflate(6.0);
        for (Entity en : level.getEntities(p, near, x -> x instanceof ServerPlayer && x != p)) {
            ServerPlayer other = (ServerPlayer) en;
            Long last = greetedAt.get(other.getUUID());
            if (last == null || now - last > 1200) {
                greetedAt.put(other.getUUID(), now);
                aimAt(p, other.position().add(0, other.getBbHeight() * 0.8, 0));
                sayAs(p, GREET_LINES[(int) (Math.random() * GREET_LINES.length)]);
                nGreet++;
                lastLineTick = now;
                ev("auto_greet", "who=" + esc(other.getName().getString()) + " n=" + nGreet
                        + " dist=" + String.format("%.1f", p.distanceTo(other)));
                return;
            }
        }
        // ② 偶尔看一眼别处 ✓（比 v2.7 稀疏：约 5 秒一次 ✓ 而且**带计数** ✓）
        if (now - lastGlanceTick > 100 && now % 20 == 0) {
            glance(p);
            nGlance++;
            lastGlanceTick = now;
            return;
        }
        // ③ ★自己溜达两下★ ✓ —— 用户明确要求"一定的自行移动"✓
        //    三条安全线 ✗：① 离锚点不超过半径 ✓ ② 目标格**先验"站得下人"** ✓
        //                  ③ 空岛护栏仍然生效 ✓（走向没支撑的格子会被它自己拦下 ✓）
        if (now - lastStrollTick > 300 && now % 40 == 0 && Math.random() < 0.35) {
            for (int k = 0; k < 8; k++) {
                double a = Math.random() * Math.PI * 2.0;
                int len = 1 + (int) (Math.random() * HUMANOID_RADIUS);
                double tx = anchorX + Math.cos(a) * len;
                double tz = anchorZ + Math.sin(a) * len;
                if (Math.hypot(tx - anchorX, tz - anchorZ) > HUMANOID_RADIUS + 0.5) {
                    continue;
                }
                if (!walkableAt(p, level, tx, tz)) {
                    continue;                           // 那一格站不下人 ⇒ 换一个 ✓
                }
                if (Math.hypot(tx - p.getX(), tz - p.getZ()) < 1.0) {
                    continue;                           // 太近 ⇒ 没意义 ✓
                }
                WalkTask t = new WalkTask((int) Math.floor(tx), (int) Math.round(anchorY), (int) Math.floor(tz),
                        now + 120, false, p.getX(), p.getZ(), now);   // 6 秒预算 ✓ 小步 ✓
                WALKS.put(p.getUUID(), t);
                nStroll++;
                lastStrollTick = now;
                ev("idle_stroll", "n=" + nStroll + " to=" + (int) tx + "," + (int) anchorY + "," + (int) tz
                        + " from=" + String.format("%.1f,%.1f,%.1f", p.getX(), p.getY(), p.getZ()));
                return;
            }
        }
        // ④ 很久没说话 ⇒ 偶尔自语一句 ✓（90~180 秒一次 ✓ 非常稀 ✓）
        if (now - lastLineTick > 2400 && Math.random() < 0.02) {
            sayAs(p, SELF_LINES[(int) (Math.random() * SELF_LINES.length)]);
            nLine++;
            lastLineTick = now;
            ev("idle_line", "n=" + nLine);
        }
    }

    /** `/dshidle status|on|off|<半径>` —— 拟人化的开关与账目 ✓（有一条算一条 ✗ 不许藏着 ✓） */
    private static int idleCmd(CommandContext<CommandSourceStack> ctx, String op, int radius)
            throws CommandSyntaxException {
        CommandSourceStack src = ctx.getSource();
        ServerPlayer p = src.getPlayerOrException();
        String o = op == null ? "status" : op.toLowerCase();
        if (o.equals("on")) {
            HUMANOID = true;
            anchorX = p.getX(); anchorY = p.getY(); anchorZ = p.getZ();
            if (radius > 0) { HUMANOID_RADIUS = Math.min(16, radius); }
            lastStrollTick = lvl(p).getGameTime();
            ev("humanoid", "on radius=" + HUMANOID_RADIUS);
        } else if (o.equals("off")) {
            HUMANOID = false;
            WalkTask t = WALKS.get(p.getUUID());
            if (t != null && !t.done && t.how.isEmpty()) {
                finish(p, t, "humanoid_off", lvl(p));
            }
            ev("humanoid", "off");
        } else if (o.equals("radius")) {
            HUMANOID_RADIUS = Math.max(1, Math.min(16, radius));
        } else if (!o.equals("status")) {
            bad(src, "dshidle: op must be status / on / off / radius <n>");
            return 0;
        }
        ok(src, "dshidle humanoid=" + HUMANOID + " radius=" + HUMANOID_RADIUS
                + " quiet_ticks=" + HUMANOID_QUIET_TICKS
                + " anchor=" + String.format("%.1f,%.1f,%.1f", anchorX, anchorY, anchorZ)
                + " looks=" + nGlance + " strolls=" + nStroll + " lines=" + nLine
                + " heard=" + nHeard + " replied=" + nReply + " greeted=" + nGreet
                + " autoeat=" + AUTO_EAT + " idlelook=" + AUTO_IDLE);
        return 1;
    }

    /** ★吃东西走真人那条路★ ✓：`ItemStack.use` ⇒ 原版会**慢慢咀嚼 1.6 秒** ✓（不是瞬间白送 ✗） */
    private static void autoEatTick(ServerPlayer p) {
        var inv = p.getInventory();
        int sel = inv.selected;
        if (inv.getItem(sel).isEdible()) {
            ItemStack s = inv.getItem(sel);
            s.use(p.level(), p, InteractionHand.MAIN_HAND);
            ev("auto_eat", "start item=" + idOf(s) + " x" + s.getCount()
                    + " food=" + p.getFoodData().getFoodLevel());
            return;
        }
        for (int i = 0; i < 9; i++) {
            if (inv.getItem(i).isEdible()) {
                inv.selected = i;                    // 下一 tick 再吃 ✓（别在这一 tick 连做两件事 ✗）
                ev("auto_eat", "select slot=" + i + " item=" + idOf(inv.getItem(i)));
                return;
            }
        }
        for (int i = 9; i < 36; i++) {
            if (inv.getItem(i).isEdible()) {
                ItemStack a = inv.getItem(sel).copy();
                ItemStack b = inv.getItem(i).copy();
                inv.setItem(sel, b);
                inv.setItem(i, a);
                ev("auto_eat", "swap slot=" + i + " -> hotbar " + sel + " item=" + idOf(b));
                return;
            }
        }
    }

    /** 空闲时看一眼别处 ✓（纯人感 ✓ 默认关 ✗ 见 AUTO_IDLE 的注释 ✓） */
    private static void glance(ServerPlayer p) {
        double a = Math.random() * Math.PI * 2.0;
        double r = 4.0 + Math.random() * 8.0;
        aimAt(p, new Vec3(p.getX() + Math.cos(a) * r,
                p.getEyeY() - 0.8 + Math.random() * 1.6,
                p.getZ() + Math.sin(a) * r));
    }
}
