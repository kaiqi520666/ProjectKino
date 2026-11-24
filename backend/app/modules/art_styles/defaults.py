"""首批 18 个纯视觉画风种子配置（供迁移脚本与初始化使用）。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SeedArtStyle:
    code: str
    label: str
    prompt: str
    sort_order: int
    is_default: bool = False


SEED_ART_STYLES: tuple[SeedArtStyle, ...] = (
    SeedArtStyle(
        code="live-action",
        label="真人电影写实",
        prompt="真人电影摄影，自然光影层次与真实材质细节，电影级色彩分级",
        sort_order=10,
        is_default=True,
    ),
    SeedArtStyle(
        code="semi-realistic-3d",
        label="半写实 3D",
        prompt="半写实 3D 渲染，精致角色建模与柔和体积光影",
        sort_order=20,
    ),
    SeedArtStyle(
        code="anime",
        label="日漫",
        prompt="现代日系 2D 动漫，干净利落线条与清透上色",
        sort_order=30,
    ),
    SeedArtStyle(
        code="suspense-horror",
        label="暗调悬疑写实",
        prompt="真人电影写实摄影，冷色调低饱和、强明暗对比与克制阴影",
        sort_order=40,
    ),
    SeedArtStyle(
        code="documentary",
        label="纪实摄影",
        prompt="真人纪实摄影，自然环境光与质朴真实质感，不过度修饰",
        sort_order=50,
    ),
    SeedArtStyle(
        code="nordic-minimalism",
        label="北欧极简摄影",
        prompt="极简摄影美学，低饱和柔和自然光与克制留白构图",
        sort_order=60,
    ),
    SeedArtStyle(
        code="pixar-style",
        label="皮克斯风格",
        prompt="电影级 3D 卡通渲染，细腻材质表现与柔和全局光照",
        sort_order=70,
    ),
    SeedArtStyle(
        code="chibi-3d",
        label="3D Q版",
        prompt="3D Q 版潮玩渲染，圆润比例与细腻柔和棚拍质感",
        sort_order=80,
    ),
    SeedArtStyle(
        code="plush",
        label="毛绒质感",
        prompt="3D 柔软毛绒定格质感，细腻织物纤维与柔和棚拍光",
        sort_order=90,
    ),
    SeedArtStyle(
        code="cel-animation",
        label="赛璐璐",
        prompt="复古手绘赛璐璐 2D 动画，清晰墨线、平涂色块与轻微胶片颗粒",
        sort_order=100,
    ),
    SeedArtStyle(
        code="shinkai",
        label="新海诚",
        prompt="高精细度 2D 动画，通透空气光感、细腻云层与戏剧化逆光",
        sort_order=110,
    ),
    SeedArtStyle(
        code="miyazaki",
        label="宫崎骏",
        prompt="温暖手绘 2D 动画，柔和笔触、水彩背景与自然光感",
        sort_order=120,
    ),
    SeedArtStyle(
        code="hidden-leaf",
        label="日系热血动画",
        prompt="日系热血 2D 动画，凌厉线条、强对比硬边阴影与动态张力",
        sort_order=130,
    ),
    SeedArtStyle(
        code="ink-painting",
        label="国风水墨画",
        prompt="中国传统水墨丹青画风，浓淡墨韵、宣纸肌理与留白意境",
        sort_order=140,
    ),
    SeedArtStyle(
        code="dunhuang-mural",
        label="敦煌壁画风",
        prompt="矿物重彩壁画画风，古朴岩彩肌理、流动线描与金箔点缀",
        sort_order=150,
    ),
    SeedArtStyle(
        code="handpainted-watercolor",
        label="手绘水彩",
        prompt="手绘水彩插画，柔和湿画晕染、透明叠色与水彩纸纹理",
        sort_order=160,
    ),
    SeedArtStyle(
        code="flat-illustration",
        label="扁平插画",
        prompt="现代扁平矢量插画，简洁几何色块与和谐配色",
        sort_order=170,
    ),
    SeedArtStyle(
        code="picture-book",
        label="儿童绘本",
        prompt="温馨手绘绘本画风，柔和粉彩笔触与明快色调",
        sort_order=180,
    ),
)
