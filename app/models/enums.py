from enum import StrEnum


class ImportStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    COMPLETED_WITH_ISSUES = "completed_with_issues"
    FAILED = "failed"


class ImportIssueLevel(StrEnum):
    WARNING = "warning"
    ERROR = "error"


class TeacherAliasStatus(StrEnum):
    MATCHED = "matched"
    PENDING_REVIEW = "pending_review"
    IGNORED = "ignored"


class TeacherRole(StrEnum):
    THEORY = "theory"
    PRACTICE = "practice"


class MeetingType(StrEnum):
    THEORY = "theory"
    PRACTICE = "practice"


class MeetingFrequency(StrEnum):
    WEEKLY = "weekly"
    BIWEEKLY_I = "biweekly_i"
    BIWEEKLY_II = "biweekly_ii"
    OTHER = "other"


class CurriculumCategory(StrEnum):
    MANDATORY = "mandatory"
    LIMITED = "limited"
    FREE = "free"
    NOT_APPLICABLE = "not_applicable"


class CurriculumCategorySource(StrEnum):
    EXPLICIT = "explicit"
    DERIVED_RULE = "derived_rule"


class CourseStrategy(StrEnum):
    PRIMARY_COURSE = "primary_course"
    MAXIMIZE_ANY_COURSE_PROGRESS = "maximize_any_course_progress"
    MAXIMIZE_ALL_COURSES_PROGRESS = "maximize_all_courses_progress"
    WEIGHTED_COURSES = "weighted_courses"


class ExternalSyncStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    FAILED = "failed"


class TeacherStatisticsMode(StrEnum):
    ALL_HISTORY = "all_history"
    SAME_SUBJECT = "same_subject"
    RECENT_HISTORY = "recent_history"
    BLENDED = "blended"


class StatisticsConfidence(StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TeacherScoreMetric(StrEnum):
    A_RATE = "a_rate"
    AB_RATE = "ab_rate"
    FAILURE_RATE = "failure_rate"
    FO_RATE = "fo_rate"
    MEAN_GRADE = "mean_grade"
