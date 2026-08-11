# ADR-0001: Installable package и слоистые границы

- Статус: Accepted
- Дата: 2026-08-11

## Контекст

Проект вырос из MVP с flat `src/*.py`. Запуск и tests полагаются на
`PYTHONPATH`, а крупные модули объединяют domain model, parsing, orchestration,
provider wiring и file I/O. Перед open-source релизом и добавлением Code
Interpreter эта структура увеличивает риск циклических зависимостей и затрудняет
contributor onboarding.

## Решение

Перенести production-код в installable package `ai_studio_agent_builder` с
границами `domain`, `application`, `builder`, `infrastructure`, `presentation` и
единственным composition root. Миграцию выполнять механическими слоями под
regression tests, не смешивая её с feature changes.

Architecture rules проверяются AST-based pytest без отдельной runtime
dependency. Ports создаются только на реальных границах provider/persistence и
не используются как формальный wrapper над каждой функцией.

Builder agents являются adapter-реализацией application-owned
`BuilderRunPort`. `BuilderConversationService` не импортирует Agents SDK,
concrete agents или `ResultAssembler`; composition root внедряет реализацию, а
application получает нормализованный `BuilderRunOutcome`.

## Рассмотренные альтернативы

### Оставить flat modules

Минимальный diff, но сохраняет repository-specific imports и ухудшает ясность
public/internal API. Отклонено для публичного релиза.

### Big-bang rewrite в строгий Clean Architecture

Даёт визуально чистое дерево, но смешивает moves, переименование и поведение в
одной долгой ветке. Отклонено из-за blast radius и сложного review.

### Инкрементальная package-миграция

Выбрана: сначала фиксируются contracts и tests, затем слои переносятся по одному
с временными shims и обязательным удалением shims до релиза.

## Последствия

Положительные:

- предсказуемые imports и installable artifact;
- явный public API;
- возможность независимо тестировать application use cases и adapters;
- review новых функций по понятным dependency rules.

Отрицательные:

- временный churn путей и imports;
- необходимость обновить Docker/Compose/docs;
- риск преждевременных абстракций, ограниченный правилом real-boundary-only.

## Контроль

- characterization tests до moves;
- architecture import/cycle tests;
- wheel/sdist import smoke;
- lint/typecheck/tests после каждого слоя;
- shims удалены до `v0.1.0`.
