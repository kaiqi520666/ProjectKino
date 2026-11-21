from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, StringConstraints, model_validator

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
CharacterId = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^C\d{2}$")]
SceneId = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^S\d{2}$")]
PropId = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^P\d{2}$")]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectSettings(Record):
    name: Text
    ratio: Literal["16:9", "9:16", "1:1", "4:3", "3:4"]
    language: Literal["zh-CN", "zh-TW", "en"] = "zh-CN"
    visualStyle: Text
    visualStyleLabel: str = ""
    episodeCount: Annotated[int, Field(strict=True, gt=0)]
    maxSegmentDuration: Literal[15, 30]
    secondsPerEpisode: Annotated[int, Field(strict=True, gt=0)] = 120
    backgroundMusic: bool = True


class Character(Record):
    id: CharacterId
    name: Text
    role: Text
    voice: str = ""


class SceneCard(Record):
    id: SceneId
    name: Text
    kind: Literal["内景", "外景"]
    time: Text
    note: str = ""


class PropCard(Record):
    id: PropId
    name: Text
    role: str = ""


class EpisodePlan(Record):
    number: PositiveInt
    title: Text
    summary: Text
    hook: Text
    suspense: Text
    ending: Text
    characterIds: list[CharacterId]
    sceneIds: list[SceneId]
    propIds: list[PropId] = Field(default_factory=list)
    sourceLines: list[tuple[PositiveInt, PositiveInt]] = Field(default_factory=list)


class World(Record):
    kind: Literal["historical", "modern", "scifi", "fantasy"]
    era: Text
    baseline: Text


class Outline(Record):
    continuity: Text
    world: World | None = None
    characters: list[Character]
    scenes: list[SceneCard]
    props: list[PropCard] = Field(default_factory=list)
    episodes: list[EpisodePlan]


class Beat(Record):
    action: str | None = None
    speaker: str | None = None
    line: str | None = None
    delivery: str | None = None

    @model_validator(mode="after")
    def one_kind(self) -> "Beat":
        has_action = self.action is not None
        has_line = self.speaker is not None or self.line is not None or self.delivery is not None
        if has_action == has_line:
            raise ValueError("每个节拍二选一：要么只有 action，要么给 speaker + line（delivery 可选）。")
        if has_line and not (self.speaker and self.line):
            raise ValueError("台词节拍需要同时给出 speaker 和 line。")
        return self


class Scene(Record):
    sceneId: SceneId
    lighting: str = ""
    characters: list[CharacterId] = Field(default_factory=list)
    props: list[PropId] = Field(default_factory=list)
    flow: Annotated[list[Beat], Field(min_length=1)]


class EpisodeDraft(Record):
    number: PositiveInt
    title: Text
    summary: Text
    hook: Text
    cliff: Text
    hookBeat: tuple[PositiveInt, PositiveInt]
    scenes: Annotated[list[Scene], Field(min_length=1)]


class Episode(EpisodeDraft):
    targetSeconds: int
    seconds: float
    script: Text
    warnings: list[str] = Field(default_factory=list)


class ScriptResult(Record):
    settings: ProjectSettings
    outline: Outline
    episodes: list[Episode]


AssetKind = Literal["character", "scene", "prop"]


class Asset(Record):
    id: Text
    kind: AssetKind
    name: Text
    description: Text
    prompt: Text
    episodeNumbers: list[PositiveInt]
    voice: str = ""


class AssetResult(Record):
    settings: ProjectSettings
    assets: list[Asset]


class StoryboardAssetRef(Record):
    id: Text
    kind: AssetKind
    name: Text


ShotSize = Literal["特写", "近景", "中景", "全景", "远景"]


class StoryboardCut(Record):
    index: PositiveInt
    seconds: Annotated[float, Field(gt=0)]
    shotSize: ShotSize
    camera: Text
    framePrompt: Text
    beats: tuple[PositiveInt, PositiveInt]


class StoryboardReference(Record):
    index: PositiveInt
    assetId: Text
    name: Text
    kind: AssetKind


class StoryboardClip(Record):
    id: PositiveInt
    durationSeconds: float
    prompt: Text
    assetIds: list[str]
    references: list[StoryboardReference] = Field(default_factory=list)
    beats: tuple[PositiveInt, PositiveInt] | None = None
    blocking: str = ""
    cuts: list[StoryboardCut] = Field(default_factory=list)


class EpisodeStoryboard(Record):
    number: PositiveInt
    assets: list[StoryboardAssetRef]
    clips: list[StoryboardClip]


class StoryboardResult(Record):
    settings: ProjectSettings
    episodes: list[EpisodeStoryboard]
