from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
from config.catalog import profile_by_id, project_by_id


class ArticleInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    project: str
    lawfirm: str
    keyword: str = Field(default='', max_length=60)
    topic: str = Field(default='', max_length=200)
    subkeywords: str = Field(default='', max_length=300)
    region: str = Field(default='', max_length=60)
    institution: str = Field(default='', max_length=100)
    lawyer: str = Field(default='', max_length=60)
    references: str = Field(default='', max_length=12000)
    min_chars: int = Field(default=1200, ge=600, le=6000)
    max_chars: int = Field(default=1800, ge=600, le=6000)
    keyword_target: int = Field(default=5, ge=2, le=12)
    pdf_privacy_confirmed: bool = False  # legacy history compatibility; never required
    privacy_identities: list[dict] = Field(default_factory=list, max_length=300)
    keyword_suggestion: dict | None = None
    count_spaces: bool = False
    mode: Literal['ai', 'demo'] = 'ai'

    @model_validator(mode='before')
    @classmethod
    def project_defaults(cls, data):
        if isinstance(data, dict):
            from config.catalog import project_by_id
            project = project_by_id(data.get('project'))
            if project:
                data = {**project['defaults'], **data}
        return data

    @field_validator('keyword', 'topic', mode='before')
    @classmethod
    def trim_required(cls, v):
        return v.strip() if isinstance(v, str) else v

    @model_validator(mode='after')
    def valid_selection(self):
        if not project_by_id(self.project) or not profile_by_id(self.lawfirm):
            raise ValueError('유효한 프로젝트와 법무법인을 선택하세요.')
        if any(value and len(value) < 2 for value in [self.keyword, self.topic]):
            raise ValueError('키워드와 주제는 입력할 경우 2자 이상이어야 합니다.')
        if self.max_chars < self.min_chars or self.max_chars - self.min_chars < 100:
            raise ValueError('글자 수 범위는 최소 100자 차이가 있어야 합니다.')
        return self


class Section(BaseModel):
    model_config = ConfigDict(extra='forbid')
    question: str = Field(min_length=1, max_length=200)
    answer: str = Field(min_length=1, max_length=1500)
    explanation: str = Field(min_length=1, max_length=4000)


class Article(BaseModel):
    model_config = ConfigDict(extra='forbid')
    titles: list[str] = Field(min_length=3, max_length=3)
    selected_title_index: int = Field(ge=0, le=2)
    introduction: str = Field(min_length=1, max_length=5000)
    sections: list[Section] = Field(min_length=3, max_length=4)
    checklist: list[str] = Field(min_length=1, max_length=8)
    conclusion: str = Field(min_length=1, max_length=3000)
    cta: str = Field(min_length=1, max_length=1500)

    @property
    def title(self):
        return self.titles[self.selected_title_index]

    @property
    def body(self):
        parts = [self.introduction]
        for s in self.sections:
            parts.extend([s.question, s.answer, s.explanation])
        parts.extend(['핵심 체크리스트', *['• ' + x for x in self.checklist], '결론', self.conclusion, self.cta])
        return '\n\n'.join(parts)

    @property
    def text(self):
        return self.title + '\n\n' + self.body
