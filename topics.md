# Vibecoding Project Library: 600 Ideas

> 600 small and medium-sized projects designed for building from scratch with AI-assisted programming.
> Each idea aims to be **demonstrable, scoped, useful, and easy to evaluate**.
> Recommended pace: complete an MVP in 0.5 to 3 days. Build the main path first, then add error handling, clear feedback, and deployment notes.

## Usage

1. Pick any idea and align on the PRD first: features, technology stack, acceptance criteria, and non-goals.
2. During the MVP stage, complete the "input → processing → output" path before adding persistence, error states, and UX polish.
3. When finished, mark the idea with `[x]` and add a short review under `done/`: one highlight, one lesson, and the launch command.
4. Rotate between categories to reduce repetition and evaluate a broader range of engineering skills.

---

## 1. Command-Line Tools (20 topics)
> Practice areas: parameter parsing, file IO, TTY interaction, cross-platform compatibility.

- [ ] 1. **Markdown Renderer**: Accept Markdown files or directories from the CLI and produce HTML or PDF with themes, a table of contents, syntax highlighting, image-path validation, and a failure report.
- [ ] 2. **Terminal Pomodoro**: Provide focus/rest cycle, keyboard control, reminder sound, daily statistics, CSV export and interruption recovery, suitable for long-term terminal use.
- [ ] 3. **Clipboard Snippet Shelf**: Save clipboard text locally, organize snippets with tags, search recent entries, pin favorites, and export a reusable collection.
- [ ] 4. **Batch Renaming Tool**: Rename files in batches with regular expressions, sequence templates, case conversion, conflict detection, a diff preview, and an undo log.
- [ ] 5. **Command Alias Organizer**: Manage shell aliases, group commands by project, preview configuration changes, detect duplicate names, and export a local configuration file.
- [ ] 6. **Git Changelog Generator**: Aggregate changes by version, date or Conventional Commit, generate Markdown/HTML, and automatically annotate breaking changes.
- [ ] 7. **JSON, YAML, and TOML Converter**: Convert between JSON, YAML, and TOML from standard input or files, validate JSON Schema, locate errors, and process directories in batches.
- [ ] 8. **Intelligent History Search**: Integrate shell history, working directory and command frequency, providing fzf interaction, contextual sorting and dangerous command confirmation.
- [ ] 9. **Terminal Typing Trainer**: Provide built-in code snippets and English passages, then track WPM, error patterns, targeted practice, and local rankings.
- [ ] 10. **Terminal LLM Client**: Support streaming output, session archiving, model configuration, `/` commands, file references, and local prompt template management.

- [ ] 301. **Environment Variable Comparator**: Compare local configuration files and exported shell values, highlight missing variables, support ignore rules, and export a Markdown report.
- [ ] 302. **Log Time Slicing Tool**: Slice large logs by time window, level and keyword, support gzip, concurrent scan, context row count and result directory index.
- [ ] 303. **Directory Volume Detective**: Scan disk usage hotspots, display tree top N, growth comparison, ignore rules and generate a cleanup suggestion list with one click.
- [ ] 304. **Local Function Benchmark CLI**: Benchmark selected local functions using fixed sample inputs, configurable repetitions, duration histograms, and saved baseline comparisons.
- [ ] 305. **Document Deadline Inspector**: Read document due dates from a CSV, group upcoming deadlines, apply reminder thresholds, and export a prioritized checklist.
- [ ] 306. **Git Workspace Snapshot**: Package uncommitted changes, stash metadata, and branch information into a recoverable snapshot with notes, listing, and rollback preview commands.
- [ ] 307. **CSV Pivot Command Line**: Group-by, aggregate, filter and sort CSV, output table or new CSV, support type inference and error row reporting.
- [ ] 308. **Terminal Workspace Launcher**: Save named working directories and command presets, open a selected workspace, show recent choices, and export launcher configuration.
- [ ] 309. **Dependency License Summary**: Scan npm/pip/go lockfile licenses, flag copyleft risks, missing licenses and generate compliance briefings.
- [ ] 310. **Image Batch Compression CLI**: Compress PNG, JPEG, and WebP files in batches with quality presets, dimension limits, dry-run preview, and before-and-after size comparisons.

## 2. Personal Productivity Web Apps (30 topics)
> Practice areas: front-end state management, local persistence, UI/UX polishing.

- [ ] 11. **Minimalist Todo**: Manage tasks and subtasks with drag-and-drop ordering, complete keyboard controls, local persistence, completion trends, and a responsive mobile layout.
- [ ] 12. **Pomodoro + Task Board**: Bind Pomodoro numbers to task cards, support drag-and-drop status, focus recording, daily/weekly statistics and abnormal interruption supplementary recording.
- [ ] 13. **Daily Standup Notebook**: Record yesterday/today/blocked items, automatically generate weekly and monthly reports, support tags, search and Markdown export.
- [ ] 14. **Habit Check-in + Heat Map**: Support multiple habits, consecutive days, re-signing rules, sign-off reminders, heat maps and data import and export.
- [ ] 15. **Markdown Notebook**: Provide folder and tag views, backlinks, full-text search, edit and preview modes, and synchronization with local files.
- [ ] 16. **Spaced Repeat Flashcards**: Implement the SM-2 review algorithm, support decks, rich text, Anki CSV import, review queues, and memory curves.
- [ ] 17. **Personal Accounting**: Support income/expense entry, automatic classification of merchants and tags, budget alerts, monthly reports and CSV import.
- [ ] 18. **Time Block Weekly Calendar**: Use drag and drop to arrange weekly plans, link with Todo, support conflict prompts, copy last week's plan and completion rate statistics.
- [ ] 19. **Inspiration Collection Box**: Support quick saving of image and text links, tags, full-text search, later processing queue and automatic content identification from the clipboard.
- [ ] 20. **Reading Tracker**: Manage books, articles, and papers, record progress, notes, excerpts, ratings, and generate annual reading statistics.
- [ ] 21. **Bookmark Manager**: Read metadata from user-saved or public links, organize tags, build a local search index, detect duplicates, and create permitted offline snapshots.
- [ ] 22. **Personal Collection Catalog**: Catalog household collections with photos, tags, storage locations, purchase notes, search, and CSV import and export.
- [ ] 23. **Daily Activity Journal**: Record daily activities, memorable moments, mood notes, and photos, then browse a calendar and export selected entries.
- [ ] 24. **Personal RSS Reader**: Subscribe to public or user-authorized RSS/Atom feeds, manage unread and starred items, index permitted article text, summarize entries, and filter by keyword.
- [ ] 25. **Travel Map**: Import tracks and photo locations, display trail maps, trip timelines, city statistics and shareable travel pages.

- [ ] 311. **Meeting Action Item Tracking Board**: Extract action items from meeting notes, bind owners and deadlines, and support overdue reminders, completion rates, and weekly review views.
- [ ] 312. **Personal Knowledge Weekly Review**: Summarize this week's notes, completed tasks and reading excerpts, automatically generate review templates, support tag filtering and export.
- [ ] 313. **Focus Whitelist Timer**: Accumulate focus time only within the allowed website/application window, displaying the number of interruptions, time period distribution and daily goal completion.
- [ ] 314. **Subscription Renewal Tracker**: Track software subscriptions, billing periods, renewal dates, costs, and cancellation links, with advance reminders and monthly totals.
- [ ] 315. **Family Shared Purchasing List**: Multiple people can check purchasing items in real time, supporting classification, commonly used templates, out-of-stock notes and historical list reuse.
- [ ] 316. **Personal Goal Milestone Wall**: Break down annual goals into milestones and checkpoints, display progress bars, risk markers and record of delays.
- [ ] 317. **Email Unsubscribe Decision Box**: Import sample mailing lists, score by sending frequency and value, mark retention/unsubscription and export action list.
- [ ] 318. **Commuting Route Memo**: Record multiple commuting plans, time consumption, costs and weather effects, and support the collection of optimal routes and notes on unusual days.
- [ ] 319. **Digital Minimalist Separation List**: Inventory accounts, files and devices, set retention rules, track cleanup progress and release space records.
- [ ] 320. **Personal Skills Matrix Board**: Maintain skills, proficiency and learning plans, associate practice tasks, and display growth trajectories and weaknesses.
- [ ] 321. **Gift Exchange Journal**: Record gifts given and received, recipients, dates, occasions, and follow-up plans, with reminders and annual summaries.
- [ ] 322. **Wardrobe Outfit Planner**: Manage clothing tags, seasons and occasions, generate a week's outfit draft, support cleaning status and missing item reminders.
- [ ] 323. **Home Appliance Care Calendar**: Schedule appliance cleaning and maintenance, show upcoming tasks, record completion notes and photos, and flag overdue items.
- [ ] 324. **Personal Creative Incubation Funnel**: Move ideas through collection, screening, prototyping, and shelving while recording rejection reasons and reactivation criteria.
- [ ] 325. **Weekend Micro-Adventure Planner**: Collect nearby activities and points of interest, generate half-day or full-day itinerary drafts, and provide budget ranges and weather alternatives.

## 3. AI Applications (30 topics)
> Practice areas: prompt engineering, RAG, streaming output, and API orchestration.

- [ ] 26. **PDF Intelligent Q&A**: Upload PDFs, build a local vector index, answer with page citations, compare multiple documents, and jump directly to cited passages.
- [ ] 27. **Long Article Summary + Mind Map**: Enter a long article or URL to generate hierarchical summary, key points, to-do extraction and Markmap/Mermaid map.
- [ ] 28. **Meeting Minutes Tool**: The system completes recording upload, transcription, speaker separation, summary, resolution, to-do attribution and minutes export.
- [ ] 29. **Resume and JD Matching Score**: Parse resume and job description, gives matching score, missing keywords, rewriting suggestions and version comparison.
- [ ] 30. **Smart Email Reply Draft**: Connect to Gmail or a local sample mailbox, generate replies based on tone, retain contextual references and support manual modification.
- [ ] 31. **AI Word Cards**: Enter words to automatically generate definitions, example sentences, IPA, root words, TTS reading and spaced review plans.
- [ ] 32. **Image Description Generator**: Upload images to generate multi-language alt text, SEO descriptions and accessibility instructions, supporting batch processing and manual editing.
- [ ] 33. **AI Speaking and Interview Coach**: Provide a practice library, live conversation, scoring criteria, pronunciation feedback, review reports, and a history of performance trends.
- [ ] 34. **Code Review Bot**: Connect to a GitHub pull-request diff, apply configurable review rules, add inline comments, classify risks, and suggest actionable fixes.
- [ ] 35. **Document Translation Preserves Typesetting**: Upload docx/pdf, retain titles, tables, and picture positions, and output bilingual previews and glossaries.
- [ ] 36. **AI Meme Generator**: Generate meme images and captions from a theme, with templates, font and outline controls, batch export, and version history.
- [ ] 37. **Article to Podcast**: Convert articles into two-person conversation scripts, generate segmented TTS audio, and support audition, regeneration, and mp3 export.
- [ ] 38. **Natural Language Schedule Assistant**: Parse expressions such as "remind me to have a meeting next Wednesday at 2 pm", generate a schedule draft and support conflict checking.
- [ ] 39. **Editorial Tone Consistency Checker**: Review a draft against an organization-owned tone guide, flag inconsistent passages, suggest neutral revisions, show a diff, and verify that factual claims remain unchanged.
- [ ] 40. **Local Knowledge Base Chat**: Import Obsidian or Notion exports, build a local index, answer with an optional online LLM, cite sources, and refresh the index.

- [ ] 326. **Code Comment Completion Workbench**: Upload code snippets to generate function-level comments and module descriptions, supporting language switching, style templates and diff preview.
- [ ] 327. **Customer Conversation Quality Reviewer**: Import sample conversations, score politeness, completeness, and prohibited terms, then provide improvement suggestions and an example library.
- [ ] 328. **Multilingual UI Copy Proofreading**: Scan interface copy CSV, check for tone consistency, length overflow and terminology uniformity, and generate a revision table.
- [ ] 329. **Requirements Clarification Questionnaire Generator**: Enter a sentence of requirements and generate a list of clarification questions, priority suggestions and assumptions, which can be exported to stakeholders.
- [ ] 330. **Test Case Draft Factory**: Generate draft boundary, error, and regression cases from a feature description, assign priorities, and export a reusable test suite.
- [ ] 331. **Release Notes Polisher**: Turn commit messages into user-facing release notes, group new features, fixes, and breaking changes, and support several tones.
- [ ] 332. **Design Draft Review Annotation Assistant**: Upload interface screenshots, automatically list usability and accessibility doubts, and support manual confirmation and export of issue lists.
- [ ] 333. **Risk Summary of Contract Terms**: Upload the contract sample text, extract key obligations, deadlines and abnormal clause summaries, and mark items that require lawyer review (not a substitute for legal advice).
- [ ] 334. **The Learning Path Orchestrator**: Generate stage paths, resource types and test checkpoints based on target skills, and support progress check-in and path adjustment.
- [ ] 335. **Log Root Cause Hypothesis Generator**: The system pastes the error stack and recent changes to generate a possible root cause ranking, verification steps and related file guesses.
- [ ] 336. **Product Naming Brainstorming Board**: Enter product positioning to generate candidate names, domain name availability reminders and trademark conflict reminder placeholders, and support voting and collection.
- [ ] 337. **Meeting Role Simulator**: Set product/R&D/operation roles, generate different position summaries on the same issue, and help rehearse alignment meetings.
- [ ] 338. **Data Field Definition Assistant**: Input table structure or sample rows to generate field business definitions, enumeration guesses, and drafts of lineage notes.
- [ ] 339. **Accessible Copy Rewriter**: Rewrite complex descriptions into more readable versions, mark reading levels, retain key terms, and display a diff of changes.
- [ ] 340. **Competitive Product Function Matrix Generation**: Import summaries of several product pages, extract a feature matrix and differentiators, rank follow-up priorities, and support manual revision.

## 4. Mini Games (20 topics)
> Practice areas: Game loop, collision detection, state machine, AI opponent.

- [ ] 41. **Snake**: Implement a Canvas or terminal version with keyboard controls, a local leaderboard, skins, pause and resume, and mobile touch input.
- [ ] 42. **2048**: Support undo, animation, keyboard/touch operations, score statistics, highest score saving and different board sizes.
- [ ] 43. **Minesweeper**: Provide custom difficulty, first point safety, flag marking, timing list, keyboard and mouse operation and failure replay.
- [ ] 44. **Tetris**: Implement hold, next block preview, ghost blocks, combo scoring, pause and adjustable fall speed.
- [ ] 45. **Gomoku with an AI Opponent**: Implement board interaction, win detection, an Alpha-Beta pruning opponent, difficulty levels, and replay history.
- [ ] 46. **Sudoku**: Support problem generation, solver, candidate number, hints, error checking, step counting and multiple difficulties.
- [ ] 47. **Chinese Idioms Wordle**: Publish one Chinese idiom puzzle each day with input validation, color feedback, hints, shareable results, and a local puzzle library.
- [ ] 48. **Breakout**: Implement physical collisions, props, level editor, health, scores and level archives.
- [ ] 49. **Canvas Arcade Shooter**: Build an arcade shooter with enemy waves, bosses, skill cooldowns, power-ups, collision detection, and a local leaderboard.
- [ ] 50. **Multiplayer Online Tic-tac-toe**: Use WebSocket rooms for matchmaking and spectating, synchronize game state, and recover cleanly after a disconnect.

- [ ] 341. **Memory Matching Game**: Implement card flipping and matching with themed decks, combo scoring, a timed mode, and a local high score.
- [ ] 342. **Pixel Parkour**: Build a side-scrolling runner with jumping, obstacle waves, power-ups, a difficulty curve, touch controls, and a local leaderboard.
- [ ] 343. **Merge Puzzle Variant**: Build a merge puzzle with a customizable item progression, editable gravity and merge rules, skins, and one-step undo.
- [ ] 344. **Text Adventure Engine**: Use JSON to configure plot nodes, options and state variables, and provide editor preview and archive reading.
- [ ] 345. **Tower Defense Basic Level**: Implement paths, turret upgrades, waves and resources, and support level configuration files and failed restarts.
- [ ] 346. **Rhythm Tapping Game**: Follow the beat and click to determine Perfect/Good/Miss. It supports custom music charts, calibration and performance ratings.
- [ ] 347. **Maze Generation and Pathfinding Demonstration**: Random maze, player control and A* demonstration layer, supporting size adjustment and algorithm step visualization.
- [ ] 348. **Two-Player Local Pong**: Implement paddle physics, scoring, optional power-ups, and pause controls for two players using split keyboard controls or touch buttons.
- [ ] 349. **Deck-Building Roguelike Prototype**: Build a combat, card-selection, and upgrade loop with visible enemy intent, deck management, and reproducible random seeds.
- [ ] 350. **City Construction Mini Sandbox**: Place buildings on a grid, manage resources and satisfaction, simulate a day-night cycle, and save the current city.

## 5. Browser Extensions (16 topics)
> Practice areas: Manifest v3, Content Script, page interaction and local preferences.

- [ ] 51. **Selection Translator with AI Explanations**: Show a translation popover for selected text with contextual explanations, examples, bookmarks, keyboard shortcuts, and compatibility with common page layouts.
- [ ] 52. **Web Page to Markdown Archive**: Archive user-authorized or public pages as Markdown, localize permitted images, preserve metadata, estimate reading time, and export a downloadable package.
- [ ] 53. **Tab Manager**: Display tab memory, grouping, one-command suspend, resume, search and session saving.
- [ ] 54. **Bilibili/YouTube Subtitle Export + AI Summary**: Read subtitles, export SRT/Markdown, and generate chapter summaries and key timestamps.
- [ ] 55. **Automatic Form Filling**: Manage multiple identity materials, support field mapping, domain name whitelist, preview confirmation and sensitive field protection.
- [ ] 56. **Manual Element Blocker**: Click on page elements to generate hidden rules, supporting rule list, switch, import and export, and site-level effect.
- [ ] 57. **Reading Mode**: Extract the main article into a distraction-free view with font, width, and theme controls, text-to-speech, a read-later list, and site-specific rules.
- [ ] 58. **Web Page Change Monitor**: Monitor a selected region on a public or user-owned page, calculate diffs, send browser notifications, and retain historical snapshots.

- [ ] 351. **Page Performance Snapshot Plug-in**: Collect LCP/CLS approximate indicators and resource waterfall summary with one click, export JSON report and annotate the big picture.
- [ ] 352. **Automatically Temporarily Save Form Drafts**: Schedule local temporary storage of editable forms, restore them with one click after a crash, and support site whitelisting and sensitive field exclusion.
- [ ] 353. **Page Heading Outline Inspector**: Extract page headings, highlight skipped levels and duplicate labels, preview the document outline, and export suggested corrections.
- [ ] 354. **Dark Mode Enforcer**: The system injects adjustable filters/CSS for dark-free sites with support for domain rules, contrast adjustments, and exclude selectors.
- [ ] 355. **Permitted Image Collection Exporter**: Select images from a user-owned or public page, filter and deduplicate permitted assets, and export them as a zip with configurable file names.
- [ ] 356. **Reading Progress Synchronization Bar**: Synchronize long text reading position across devices (export code or local account simulation), display percentage and last reading time.
- [ ] 357. **Browser Reading List Organizer**: Collect pages into a reading list, add priorities and tags, search saved entries, and import or export a local collection.
- [ ] 358. **Page Typography Previewer**: Preview font families, line spacing, text width, and heading scales on the current page, save named presets, and reset changes.

## 6. Data Visualization and Dashboard (20 topics)
> Practice areas: chart library, time series data, real-time updates, information density design.

- [ ] 59. **GitHub Contribution Analysis**: Pull public GitHub data to display languages, projects, stars, contribution heat maps and trend comparisons.
- [ ] 60. **Cryptocurrency/stock Real-time Disk**: Implement watchlists, real-time prices, K-lines, rise and fall alerts and local investment notes.
- [ ] 61. **Small-Screen Weather and Air Quality Dashboard**: Optimize a full-screen dashboard for an old phone or Raspberry Pi, showing weather, AQI, alerts, a clock, and automatic refresh.
- [ ] 62. **Home Smart Device Dashboard**: Simulate the HomeAssistant style and manage device status, scene linkage, historical curves and offline prompts.
- [ ] 63. **Local Build Duration Dashboard**: Import build logs and show duration trends, slow stages, result counts, and comparisons between saved runs.
- [ ] 64. **Personal Consumption Sankey Chart + Waterfall Chart**: Import bill CSV, automatically classify, display fund flow, budget balance and abnormal consumption.
- [ ] 65. **Team Efficiency Analysis**: Pull Jira/Linear sample data and analyze cycle time, congestion points, throughput and member load.
- [ ] 66. **Reading Pace Dashboard**: Import reading sessions and page counts, display weekly progress, completion estimates, and comparisons by book or genre.
- [ ] 67. **Paper Citation Network Graph**: Analyze paper citation data and use D3 to display force-directed graphs, key nodes, clustering and search positioning.
- [ ] 68. **Company News Sentiment Dashboard**: Read public news feeds or local samples, classify sentiment, cluster topics, show a timeline, and highlight items for review.

- [ ] 359. **Open Source Project Activity Dashboard**: Import issue/PR sample CSV to display throughput, shutdown duration, contributor distribution and activity trends.
- [ ] 360. **Team Duty Heat Map**: Show daily duty coverage, conflicts and vacancies, and support importing schedules and exporting adjustment suggestions.
- [ ] 361. **Workshop Delivery Punctuality Wall**: Import delivery schedules and completion dates, calculate on-time rates, group delays by team, and export monthly comparisons.
- [ ] 362. **Content Release Rhythm Calendar**: Visualize multi-channel release records as calendar heat, marking gap weeks and peak days.
- [ ] 363. **Warehouse Space Utilization Map**: Display warehouse utilization, dwell time, and picking hot spots as a heat map, with filtering by SKU category.
- [ ] 364. **Campus Schedule Conflict Map**: Import courses and classroom occupancy, highlight conflicts, idle classrooms and suggested class adjustment windows.
- [ ] 365. **Customer Service Ticket Stacking Funnel**: Display the new/processing/waiting/closed funnel, as well as the average response and resolution time trends.
- [ ] 366. **Equipment Inspection Completion Rate Dashboard**: Display the inspection plan completion rate, missed inspection points, and photo inspection entrances by route and owner.
- [ ] 367. **Event Registration Conversion Funnel**: Visualize sample conversion data from impressions through clicks, form completion, and payment, with comparisons across channels.
- [ ] 368. **Local Weather Comparison Dashboard**: Compare temperature and precipitation across saved cities, annotate thresholds, and export the resulting chart as an image.

## 7. Automation and Scripting (20 topics)
> Practice areas: scheduled tasks, file processing, reminders, error recovery.

- [ ] 69. **Daily News Digest**: Read public RSS feeds or approved web sources, deduplicate and classify entries, generate concise summaries, and deliver a scheduled email or chat digest.
- [ ] 70. **Personal Media Library Organizer**: Parse user-provided feed metadata and local media files, rename and classify files, fetch permitted artwork, and report duplicates without downloading protected content.
- [ ] 71. **WeChat / Telegram Robot**: Integrate reminders, weather, morning reports, queries and command help, and support multi-user permissions.
- [ ] 72. **Screenshot + OCR Archiving**: Monitor clipboard screenshots, automatically OCR, tag, save original images and perform full-text search.
- [ ] 73. **Recurring Routine Reminder**: Manage recurring personal routines, flexible schedules, missed-item reminders, completion notes, weekly summaries, and notification preferences without logging in to third-party accounts.
- [ ] 74. **Folder Organizer**: Archive files by type, date, project rules, provide dry-run, undo and conflict handling.
- [ ] 75. **Video Clipping by Keyword**: Read subtitles, locate clips by keyword, call ffmpeg to slice and generate a preview list.
- [ ] 76. **Public Event Availability Digest**: Read public or sample event feeds, summarize schedule and availability changes, send a digest, and keep a change history without booking or reserving anything.
- [ ] 77. **Event Planning Checklist**: Track event dates, public sales announcements, attendee reminders, accessibility notes, and a manual preparation checklist without automating login, purchase, or reservation flows.
- [ ] 78. **Automatic Weekly Report Generation**: Summarize git commits, schedules, message records, and manual additions to generate an editable weekly report draft.

- [ ] 369. **Screenshot Regression Comparison Pipeline**: Capture approved pages on a schedule, compare screenshots against a baseline, and produce a visual diff report with threshold alerts.
- [ ] 370. **Backup Integrity Inspection**: Check the backup directory size, timestamp and sample decompression, sends a notification in case of failure and retains the inspection log.
- [ ] 371. **Email Attachment Archiving Robot**: Pull attachments and archives them into a directory structure according to rules, renames them and writes index JSON.
- [ ] 372. **Folder Change Journal**: Record local file additions, edits, and removals on a schedule, show a change timeline, and export selected observations.
- [ ] 373. **Dependency Update PR Pre-check**: Run installation and smoke scripts on the dependency upgrade branch, summarize the logs and mark merging suggestions.
- [ ] 374. **Static Asset Size Reporter**: Inspect a local build folder, group assets by type and size, compare saved snapshots, and export a size-budget report.
- [ ] 375. **Conference Room Preparation Checklist**: Track furniture, presentation materials, seating, and room setup before meetings, assign owners, and retain completion notes.
- [ ] 376. **Multi-Environment Configuration Drift Scanner**: Compare configuration keys across environments, report missing, extra, and differing values, and generate a draft synchronization ticket.
- [ ] 377. **Image Watermark Batch Processor**: Add watermarks, resize images, and convert formats in batches, with reusable templates and dry-run preview.
- [ ] 378. **Slack/Feishu Daily Summary Script**: Pull tagged messages from Slack or Feishu, generate a structured daily digest, and deliver it to a selected conversation.

## 8. Content Creation Tools (16 topics)
> Practice areas: Canvas/SVG, real-time collaboration, exporting to multiple formats.

- [ ] 79. **Online Whiteboard**: Provide drawing tools, shapes, text, selection, undo, export, and lightweight collaboration in an MVP inspired by Excalidraw.
- [ ] 80. **Mini CodePen**: Offer side-by-side HTML, CSS, and JavaScript editors with a live preview, error capture, local saves, and shareable links.
- [ ] 81. **Resume Builder**: The system offers multiple templates, structured forms, live preview, PDF export, ATS-friendly checking and version management.
- [ ] 82. **Business Card/Poster Generator**: Edit text, images, colors, and dimensions in reusable templates, preview the result, and export PNG or PDF files.
- [ ] 83. **Markdown Collaborative Editing**: Enable multi-person real-time editing, cursor display, version history, preview and conflict recovery.
- [ ] 84. **SVG Icon Library + Online Editor**: Manage icon collections, support path transformation, color replacement, code copying and batch export.
- [ ] 85. **PPT Automatically Generated**: Enter the outline to generate slide structure, layout, picture placeholders, lecture notes and downloadable files.
- [ ] 86. **Video Subtitle Generation**: Upload audio and video, call transcription, generate bilingual subtitles, edit timeline, and burn and export.

- [ ] 379. **Storyboard Timeline**: Manage shots, duration, narration, and asset status, then export a production checklist and compare versions.
- [ ] 380. **Subtitle Timeline Refiner**: Import SRT, support waveform alignment, batch offset, merge split sentences and style preview.
- [ ] 381. **Cover Template Batch Rendering**: Use template + CSV to batch generate cover images, supporting font safe zone and export specification verification.
- [ ] 382. **Podcast Chapter Marker**: Mark chapter points on the audio timeline, generate show notes drafts and platform chapter formats.
- [ ] 383. **Material Copyright Source Ledger**: Register material sources, license types, expiration dates and used works, and prompt risks during retrieval.
- [ ] 384. **Long Article Structure Outline Editor**: Edit chapters, arguments and evidence links in a tree view, export to Markdown and check for dangling references.
- [ ] 385. **Brand Tone Checklist**: Scan the manuscript against the tone guidelines, mark violating sentences and provide replacement suggestions.
- [ ] 386. **Multi-Platform Title Lab**: Generate title variations for the same content, record sample click feedback, and capture the patterns behind the strongest options.

## 9. Education and Learning Tools (12 topics)
> Practice areas: interactive animation, sandbox execution, visual teaching.

- [ ] 87. **Coding Practice Platform**: Provide a project list, code editor, local evaluator, timer, mistake review notebook, and submission history.
- [ ] 88. **Algorithm Visualization**: Demonstrate sorting, shortest-path, and dynamic-programming algorithms with step controls, adjustable speed, custom input, and explanatory text.
- [ ] 89. **Live Formula Rendering Playground**: Provide a KaTeX and Mermaid practice area with live preview, precise error locations, and reusable templates.
- [ ] 90. **Multilingual Read-Aloud Practice**: Display practice text, record and play back speech, score pronunciation, locate likely errors, and generate a repetition plan.
- [ ] 91. **Code Translation Playground**: Translate examples between Python, JavaScript, and Go while showing diffs, runnable samples, and semantic caveats.
- [ ] 92. **SQL Sandbox**: Provide sample databases and exercises from basic queries through window functions, with execution, result comparison, and hints.

- [ ] 387. **Mistake Review Organizer**: Record missed problems, concepts, and mastery levels, then build a review queue and a weak-area radar chart.
- [ ] 388. **Classroom Random Student Picker**: Select students with configurable weights, avoid immediate repeats, retain history, support groups, and present clearly on a classroom display.
- [ ] 389. **Experiment Report Template Assistant**: Generate report skeleton according to subject templates, check the completeness of required paragraphs and export to PDF/Markdown.
- [ ] 390. **Vocabulary Self-test Web**: Graded vocabulary list sampling, record accuracy curve and recommended review list.
- [ ] 391. **Programming Assignment Feedback Prototype**: Run fixed tests against student code and generate a pass matrix with safe, common-error feedback in a sandboxed demonstration.
- [ ] 392. **Parent-Teacher Meeting Notes Planner**: Help teachers record student strengths, areas for improvement, action plans, meeting talking points, and follow-up dates.

## 10. Creativity and Experimentation (16 topics)
> Practice areas: graphics/audio processing, cross-device experience, AI gameplay innovation.

- [ ] 93. **Pixel Artboard + GIF Export**: Implement grid drawing, palette, layers, onion skinning, frame animation and GIF export.
- [ ] 94. **Metronome + Rhythm Training**: Provide BPM, time signature, visual feedback, auditory feedback, rhythm practice and accuracy statistics.
- [ ] 95. **Minimalist DAW**: Support multi-track recording, waveform display, editing, volume adjustment, beat grid and wav export.
- [ ] 96. **ASCII Art Generator**: Upload images to character art, support density, character set, width, inverse color and text/image export.
- [ ] 97. **AI Ancient Poetry Generator**: Generate ancient poems based on subject matter, meter, and rhyme, and display them for checking, rewriting, and collecting.
- [ ] 98. **Tarot Divination Web Application**: Implement card drawing, card formation, AI interpretation, historical records, sharing pictures and disclaimers.
- [ ] 99. **AR Business Card**: Generate a QR code, and WebXR displays the 3D business card, contact information and interactive effects after scanning the code.
- [ ] 100. **Multi-person Collaboration Drawing Board**: Implement low-latency WebSocket synchronization, user cursor, undo stack, room management and disconnection recovery.

- [ ] 393. **Generate Artistic Parameter Sandbox**: Use sliders to control real-time preview of noise/color/symmetry parameters, support random seeds and export PNG.
- [ ] 394. **Audio Visualization Playground**: Drive particles and waveforms from microphone input, offer several visual styles, and include a placeholder workflow for screen-recording export.
- [ ] 395. **ASCII Animation Editor**: Edit frame-based ASCII animations with onion-skin preview, adjustable playback speed, and text or JSON export.
- [ ] 396. **Pixel Painting Collaboration Canvas**: Grid pixel painting, color palette, undo and redo, optional sharing of read-only links.
- [ ] 397. **Story Dice Inspirer**: Random character/scene/conflict combinations, save inspiration cards and expand short outlines.
- [ ] 398. **Font Pairing Lab**: Preview heading and body font combinations, adjust weight and line height, and export reusable CSS snippets.
- [ ] 399. **Mini Physics Sandbox**: Simulate 2D rigid bodies, gravity, and constraints, let users place shapes, and save parameter presets.
- [ ] 400. **Color Accessibility Contrast Check**: Enter a pair of colors, calculate their contrast ratio, report WCAG AA and AAA results, and suggest accessible alternatives.

## 11. Developer Tools and Engineering Platforms (40 topics)
> Practice areas: code analysis, building experience, team collaboration, and engineering observability.

- [ ] 101. **Local API Mock Studio**: Define REST endpoints visually, configure response templates, delays, and error rates, generate a mock server, and record request logs.
- [ ] 102. **OpenAPI Document Comparator**: Compare two OpenAPI files, marking additions, deletions, compatibility risks, and migration recommendations.
- [ ] 103. **Database Schema Diff Tool**: Read two SQLite/PostgreSQL schemas and output table field differences, index differences and migration SQL drafts.
- [ ] 104. **Environment Template Comparator**: Compare project configuration templates, highlight missing and unused keys, group differences by file, and export a review checklist.
- [ ] 105. **Dependency License Dashboard**: Parse package/requirements/go.mod, display licenses, version risks, upgrade recommendations and export reports.
- [ ] 106. **Code Snippet Knowledge Base**: Collect reusable team snippets with tags, search, configurable placeholders, one-click copying, and usage statistics.
- [ ] 107. **CLI Task Running Panel**: Register commonly used commands as tasks and provide parameter forms, real-time logs, exit codes and history records.
- [ ] 108. **Local CI Prefinger**: Read project configuration, concatenates lint/test/build, and aggregate error summaries and fix suggestions on failure.
- [ ] 109. **Log Pattern Miner**: Import log files, automatically cluster similar errors, and count frequency, time distribution and sample context.
- [ ] 110. **Feature Flag Manager**: Manage local feature flags, environments, user targeting rules, and evaluation logs, and provide front-end SDK examples.
- [ ] 111. **PR Review Checklist Generator**: Generate reviewer checklist based on diff and project rules, categorizes by risk and support Markdown export.
- [ ] 112. **Code Complexity Radar**: Scan function length, cyclomatic complexity, duplicate code and dependencies, and output visual hot spots.
- [ ] 113. **Repository File Convention Checker**: Check file names, folder structure, trailing whitespace, and required project documents against configurable conventions and export suggested edits.
- [ ] 114. **Docker Compose Visualizer**: Parse compose files, displaying service dependencies, ports, volumes, environment variables, and health check gaps.
- [ ] 115. **Error Code Dictionary Manager**: Maintain product error codes, user texts, troubleshooting steps and multi-language translations, and support search and export.
- [ ] 116. **Database Query Favorites**: Save commonly used SQL, parameter templates, execution history, result previews and sensitive field masks.
- [ ] 117. **Lightweight Release Checkbench**: Manage version numbers, change lists, rollback steps, release approvals, and post-release verification items.
- [ ] 118. **Local Event Timeline Explorer**: Import JSON event samples, filter by type and time, inspect payload fields, compare related events, and export selected records.
- [ ] 119. **Package Volume Analyzer**: Analyze front-end build products or static directories to display large files, duplicate resources, and compression gains.
- [ ] 120. **Project Tool Version Checklist**: Compare local Git, Node, Python, and package-manager versions with project requirements and show a reproducible setup checklist.

- [ ] 401. **API Fault Injection Matrix**: Configure delay, 5xx, empty response and current limiting combinations by interface, generate reusable fault scenarios and export them to joint debugging parties.
- [ ] 402. **Development Fixture Library**: Manage reusable local fixture files, attach descriptions and tags, preview contents, compare versions, and export selected bundles.
- [ ] 403. **Change Impact Test Selector**: Map changed files to relevant test directories and output a recommended regression suite with identified coverage gaps.
- [ ] 404. **Feature Switch Console**: Manage feature flags, audience percentages and audit logs, and provide local coverage mode.
- [ ] 405. **Dependency Upgrade Planning Board**: Record desired dependency versions, compatibility notes, owners, target dates, and completed verification steps in an upgrade checklist.
- [ ] 406. **Database Migration Previewer**: Parse the migration file and display the sequence, dangerous operation flags, and whether the rollback script exists.
- [ ] 407. **Container Image Layer Analyzer**: Analyze the historical image layer size and file contribution, and mark the fat layer and optimization points.
- [ ] 408. **Local Message Queue Observation Platform**: Visualize queue depth, consumption delay and dead letters, and support replaying sample messages.
- [ ] 409. **Code Owner Coverage Check**: Check CODEOWNERS against the directory structure to identify unowned paths and conflicting rules.
- [ ] 410. **Release Product Verification Bench**: Verify artifact checksums, signatures, and version metadata, then record the result in a release inventory.
- [ ] 411. **One-click Initialization of the Development Environment**: Install dependencies according to the project template, copy env samples and run health checks, and output failure steps.
- [ ] 412. **GraphQL Query Workbench**: Support schema browsing, query collections, variable templates, and history.
- [ ] 413. **Contract Test Results Wall**: Aggregate consumer contract results, displaying breaking changes and owners by service.
- [ ] 414. **Source Code Comment To-do Radar**: Scan TODO/FIXME and associates owners with deadlines to generate a cleanup sprint list.
- [ ] 415. **Branch Lifecycle Monitor**: Track long-lived branches, commits behind the main branch, and recent activity, then remind owners to merge or archive stale work.
- [ ] 416. **Error Code Dictionary Center**: Maintain error codes, meanings, user texts and troubleshooting links, and support search and versions.
- [ ] 417. **Local Multi-Service Process Orchestrator**: Start local front-end and worker processes from configuration, colorize combined logs, and stop every managed process with one command.
- [ ] 418. **SQL Slow Query Sample Library**: Include slow SQL, execution plans and optimization records, and support tags and comparison before and after.
- [ ] 419. **Sample Event Rule Playground**: Apply configurable rules to imported JSON event samples, show matching decisions and transformations, and compare rule versions.
- [ ] 420. **Scaffolding Template Market Local Version**: Browse local project templates, substitute variables, preview the generated file tree, and lock template versions.

## 12. Collaboration and Real-Time Systems (30 topics)
> Practice areas: shared editing, conflict handling, activity views, updates.

- [ ] 121. **Team Decision-making Voting Room**: Create polls with anonymous or named voting, live results, deadlines, export, and role-based access controls.
- [ ] 122. **Real-Time Queue and Calling System**: Issue queue numbers, call the next visitor, show service-window status, estimate waiting time, and drive a large display.
- [ ] 123. **Multi-person Demand Priority Matrix**: The team drags the demand card to the value/cost matrix, synchronizes it in real time and generates ranking suggestions.
- [ ] 124. **Online Planning Poker**: Complete closed loop of rooms, members, story point voting, reveals, statistics and history.
- [ ] 125. **Shared Clipboard Workspace**: Share short text, links, and file snippets within a team space, with expiration, search, and access controls.
- [ ] 126. **Collaborative JSON Editor**: Multiple people can edit JSON, supporting schema verification, formatting, conflict prompts and version rollback.
- [ ] 127. **Real-time Status Wall**: Team members update status, blocked items, and items being processed, supporting filtering and automatic expiration.
- [ ] 128. **Small Customer Service Workbench**: Simulate visitor messages, customer service assignments, quick replies, session status and satisfaction records.
- [ ] 129. **Multiplayer White Noise Room**: Shared playlists, synchronized playback status, room chat and focus timing.
- [ ] 130. **Event Registration and Sign-in System**: Event creation, registration form, QR code sign-in, list export and lateness statistics.
- [ ] 131. **Team Knowledge Card Review**: Members submit knowledge cards, others comment, vote, mark as expired and generate a review queue.
- [ ] 132. **Online Shift Scheduler**: Configure members, holidays, rules and fairness indicators to automatically generate an adjustable schedule.
- [ ] 133. **Light Incident Command Room**: Record the incident timeline, owner, status, action items and review export.
- [ ] 134. **Remote Pair Programming Timer**: Share Pomodoros, role rotations, notes and post-meeting action items, with room link support.
- [ ] 135. **Live Interactive Barrage Wall**: Receive simulated barrage and support keyword filtering, lottery, voting and large screen mode.

- [ ] 421. **Multi-person Whiteboard Note Wall**: Let several participants move notes in real time, apply colors, vote, organize rooms, and export the board as an image.
- [ ] 422. **Pair Programming Session Timing**: Alternate driving/navigation role timing, record issues and review notes.
- [ ] 423. **Shared Cursor Presentation Mode**: The host shares the mouse track and highlight circle, and the audience follows the page scrolling (demo level).
- [ ] 424. **Team Heartbeat Stand-up Board**: Real-time summary of each person's three-sentence status, supporting blocking marking and post-meeting archiving.
- [ ] 425. **Online Voting and Point Estimator**: Plan poker-style point estimation, revealing the hidden votes before and after, discussion notes and final consensus.
- [ ] 426. **Shared Release Countdown Wall**: Show a synchronized countdown, checklist completion, blockers, and a go/no-go decision to every participant.
- [ ] 427. **Multi-person Outline Editing**: Real-time editing of tree outlines, locking nodes and comment bubbles, and supporting version snapshots.
- [ ] 428. **Remote Design Walkthrough Room**: The system synchronously browse design draft hot spots, collect comment timelines and decision status.
- [ ] 429. **Conference Room Occupancy Real-time Board**: Display room occupancy, reservations and next meeting, and support quick extension application.
- [ ] 430. **Incident Bridge Minutes Board**: Record events, decisions and participants in real time during the accident, and automatically generate a timeline for export.
- [ ] 431. **Shared Clipboard Team Edition**: Short-term sharing of text snippets to team rooms, automatic expiration and access auditing.
- [ ] 432. **Online Q&A Queuing System**: Students raise their hands to line up, the instructor takes orders, and the conversation is timed to count the waiting time.
- [ ] 433. **Multi-end Presentation Teleprompter Synchronization**: The speaker and teleprompter screen scroll simultaneously, supporting font size and segmentation marks.
- [ ] 434. **Real-time Questionnaire Pulse**: Push single-question voting, real-time columnar results and anonymous mode during the meeting.
- [ ] 435. **Collaborative Checklist Room**: Let multiple roles complete the same release-day checklist while showing progress, ownership, and blocking comments.

## 13. Business and Operational Tools (30 topics)
> Practice areas: form process, data dashboard, permissions, import and export.

- [ ] 136. **Small CRM**: Manage accounts, contacts, follow-ups, sales stages, reminders and funnel reports.
- [ ] 137. **Inventory Warning System**: Maintain products, inventory changes, thresholds, suppliers and warning notifications, and support CSV import.
- [ ] 138. **Quotation Generator**: Enter customers, projects, products and discounts, generate PDF quotations and retain version history.
- [ ] 139. **Work Order Flow System**: Submit work orders, assign handlers, status flow, priority, comments and SLA statistics.
- [ ] 140. **Subscription Revenue Dashboard**: Import subscription data, calculate MRR, churn rate, renewal reminders and customer stratification.
- [ ] 141. **Content Scheduling Calendar**: Manage channels, topic selection, owner, status, release time and material links.
- [ ] 142. **Activity Budget Tracker**: Record budget items, actual expenditures, approval status and overspending warnings, and output reports.
- [ ] 143. **Customer Service FAQ Maintenance Desk**: Manage questions, answers, tags, versions, hit statistics and reminders to be updated.
- [ ] 144. **Questionnaire Results Analyzer**: Create questionnaires or import CSV to display option distributions, cross-analysis and open question summaries.
- [ ] 145. **Store Shift Scheduling and Attendance**: Configure employees, shifts, leave requests, punch-in records and anomaly reminders, and generate monthly statistics.
- [ ] 146. **Invoice Header Manager**: Save company header, tax ID, address, invoicing history and one-command copy.
- [ ] 147. **Supplier Rating Sheet**: Record delivery, price, quality and communication scores, generate radar charts and re-evaluation reminders.
- [ ] 148. **Sales Lead Deduplication Tool**: Import leads from multiple sources, remove duplications by phone number, email address and company name, and output the merged results.
- [ ] 149. **Project Cost Estimator**: Generate estimates by person-day, role, risk factor and outsourcing cost, and support scenario comparison.
- [ ] 150. **Store Customer Flow Heat Map**: Import customer flow data in time periods to display heat maps, peak and valley analysis and shift scheduling suggestions.

- [ ] 436. **Store Shift Conflict Detection**: Enter shifts and employee skills, detect overtime, consecutive shifts and gaps, and output adjustment suggestions.
- [ ] 437. **Promotional Event Calendar Desk**: Manage event schedules, channels, and asset status to avoid conflicts in the same schedule and remind you of upcoming launches.
- [ ] 438. **Member Points Rule Simulator**: Configure points acquisition/consumption rules, and use sample orders to preview points changes and abnormal boundaries.
- [ ] 439. **Supplier Delivery Tracking Board**: Record PO, promised delivery, actual arrival and delay reasons, and display supplier on-time rate.
- [ ] 440. **Price Tag Change Approval Flow**: Submit price changes, affect SKU and effective time, support approval, rejection and effective receipt.
- [ ] 441. **Offline Activity Material List**: Manage material type, quantity, owner and packing status, and support receipt verification.
- [ ] 442. **Customer Complaint Upgrade Routing Table**: Configure upgrade paths and SLAs according to problem types, simulate work order flow and count timeouts.
- [ ] 443. **Channel Commission Settlement Form**: Enter orders and channel rules, and generate payable details and discrepancy verification views.
- [ ] 444. **Store Inspection Scorecard**: Score inspection items on mobile, attach photos, create corrective tasks, and summarize store rankings.
- [ ] 445. **Inventory Transfer Suggestion Tool**: Provide a list of transfer suggestions based on sales volume and inventory level, and support manual adjustment and export.
- [ ] 446. **Contract Renewal Reminder Desk**: Manage customer contract expiration date, renewal owner and negotiation status, and provide advance reminders.
- [ ] 447. **Quotation Version Comparison**: Maintain quotation versions, term differences and customer feedback, and generate a comparison table.
- [ ] 448. **Group Purchase Progress Wall**: Display the target number of people, current progress, urging records and failed return.
- [ ] 449. **After-sales Parts Application Desk**: Register faulty models, parts requirements, approval and delivery status, and collect statistics on high-frequency parts.
- [ ] 450. **Store Energy Consumption Weekly Report**: Enter water and electricity usage, compare it with prior periods, flag unusual days, and generate a weekly report.

## 14. AI Agents and Automated Workflows (40 topics)
> Practice areas: tool invocation, state machine, queue, manual confirmation.

- [ ] 151. **Research Data Collection Agent**: Search approved public sources or import local material for a topic, remove duplicates, summarize findings, cite sources, and produce a reading list.
- [ ] 152. **Codebase Q&A Agent**: Index repository files and answer architecture or implementation questions with file citations and confidence levels.
- [ ] 153. **PR Repair Suggestion Agent**: Read failed tests and diffs, generate repair plans, patch suggestions and risk descriptions, and does not automatically submit them.
- [ ] 154. **Customer Service Diversion Agent**: The system classifies user messages, extracts entities, recommends FAQs, and forwards low-confidence requests to manual work.
- [ ] 155. **Procurement Price Comparison Agent**: Import user-provided quotations or read approved supplier feeds, normalize specifications, and compare prices, delivery dates, and stated risks.
- [ ] 156. **Personal Calendar Agent**: Read to-do, calendar and email summaries, proposes a draft schedule and waits for confirmation.
- [ ] 157. **Web Page Data Monitoring Agent**: Monitor changes in specified web pages, determine whether they are important, generate summaries and push notifications.
- [ ] 158. **Log Troubleshooting Agent**: Input logs and configurations, automatically extract abnormal patterns, search historical cases, and output troubleshooting steps.
- [ ] 159. **Data Cleaning Agent**: Import dirty CSV, identifies missing, anomalies and duplications, and generate a reviewable cleaning plan.
- [ ] 160. **Learning Path Planning Agent**: Generate courses, exercises, and review plans based on goals and time, and adjusts them according to progress.
- [ ] 161. **Document Consistency Check Agent**: Compare README, API documentation and code interfaces to find out-of-date descriptions and missing examples.
- [ ] 162. **Candidate Screening Agent**: Parse resumes, job requirements and interview feedback to generate structured scores and follow-up suggestions.
- [ ] 163. **Multi-step Form Filling Agent**: The system maps natural language requirements to complex forms, confirms key fields step by step and generates submission previews.
- [ ] 164. **Social Media Comment Processing Agent**: Cluster comments, identifies negative feedback, generate reply drafts, and upgrades processing lists.
- [ ] 165. **Meeting Action Item Tracking Agent**: Extract action items from minutes, track the status, regularly reminds the owner and summarize the progress.
- [ ] 166. **Contract Risk Scanning Agent**: Upload the contract text, mark payment, breach of contract, deadline and other risk terms and generate a list of issues.
- [ ] 167. **Experiment Report Generation Agent**: Import experimental data, charts and notes, and generate conclusions, anomaly analysis and next step suggestions.
- [ ] 168. **Multi-tool Travel Planning Agent**: Integrate budget, city, weather and route constraints to generate a modifiable itinerary draft.
- [ ] 169. **Issue Triage Agent**: Read the issue title text, automatically labels, estimates priority, finds similar issues and recommends the owner.
- [ ] 170. **Content Reuse Agent**: Split long articles into Weibo, public accounts, Xiaohongshu and email versions, retaining the core points and adapting the tone.

- [ ] 451. **Multi-source Information Morning Report Agent**: Aggregate approved RSS or public web summaries, deduplicate and cluster entries, and deliver a structured morning report.
- [ ] 452. **Work Order Triage Agent**: Recommend a category, priority, and knowledge-base links from each work-order description, then send the item to a triage queue after manual confirmation.
- [ ] 453. **Codebase Navigation Agent**: Answer where a requested function is implemented and return cited file paths with concise explanations.
- [ ] 454. **Meeting Arrangement Coordination Agent**: Collect participants' availability and preferences, proposes time candidates and generate invitation drafts.
- [ ] 455. **Change Risk Preflight Agent**: Read PR description and diff summary, list risk points, test suggestions and rollback concerns.
- [ ] 456. **Document Expiration Scan Agent**: Compare the document update date and related code submissions, and mark possible expired chapters.
- [ ] 457. **Product Update Digest Agent**: Read public release notes, summarize new features and wording changes, cite sources, and produce a weekly digest.
- [ ] 458. **Inbound Data Cleaning Agent**: The system cleans CSV according to rules, reports correction items, discarded rows and manual samples for review.
- [ ] 459. **Release Checklist Agent**: Generate or checks release check items based on service type and blocks unfinished items.
- [ ] 460. **Customer Service Macro Reply Arrangement Agent**: The system recommends macro templates based on intent and fills in slots, and sends simulations after manual editing.
- [ ] 461. **Research Evidence Card Agent**: Convert user-provided or public articles into claim-and-evidence cards with tags and citation links.
- [ ] 462. **Demo Station Form Filling Agent**: The system automatically fills in the form at the controlled demo station and takes screenshots for verification, and locates the fields if it fails.
- [ ] 463. **Log Noise Reduction Agent**: Cluster repeated log patterns, recommends sampling or ignoring rule drafts.
- [ ] 464. **Dependency Upgrade Test Agent**: Try a small dependency upgrade on an isolated branch, run the selected tests, and summarize results and conflicting files.
- [ ] 465. **Content Compliance Preliminary Review Agent**: Scan the copy for sensitive words and exaggerated expressions (configurable word list), and output modification suggestions.
- [ ] 466. **Weekly Plan Dismantling Agent**: Split the goal into executable tasks, estimated time and dependencies, and write it into a Kanban draft.
- [ ] 467. **API Sample Generation Agent**: Generate multi-language call samples and error handling snippets from OpenAPI.
- [ ] 468. **Incident Review Draft Agent**: Input timeline materials to generate review structure, root cause candidates and improvement items list.
- [ ] 469. **Multi-tool File Sorting Agent**: The system renames the archive download directory according to rules, requests confirmation and writes operation logs in case of conflicts.
- [ ] 470. **Learning Coach Dialogue Agent**: Ask questions from a course outline, evaluate short answers, record mastery, and generate review points for the next session.

## 15. Hardware, Edge, and Local-First Apps (30 topics)
> Practice areas: local storage, offline experience, device adaptation, sensor data.

- [ ] 171. **Offline Family Recipe Box**: Save recipes, ingredients, steps, and photos locally, with offline search, shopping lists, and serving-size conversion.
- [ ] 172. **Raspberry Pi E-Ink Calendar**: Generate calendar images suitable for ink screens, including weather, schedule, to-do and low-power refresh strategies.
- [ ] 173. **Local Photo Deduplicator**: Scan photo directories, finds duplicates by hash and similarity, and provide preview, retention rules and recycle bin.
- [ ] 174. **Home Media Indexer**: Scan local video and music folders, read embedded metadata or approved public catalogs, and provide search, artwork, and playback history.
- [ ] 175. **Local File Packaging Desk**: Select local files, preview folder structure and archive size, apply naming templates, create a zip, and keep package history.
- [ ] 176. **Bluetooth Device Power Display Board**: Read or simulate Bluetooth device power, display status, low battery reminder and historical trends.
- [ ] 177. **Sensor Data Logger**: Receive data such as temperature and humidity, implement local SQLite, display curves, threshold alarms and export.
- [ ] 178. **Offline Map Annotator**: Load offline map tiles or static basemaps, add markers, paths, notes and export.
- [ ] 179. **Local Music Practice Accompaniment**: Manage accompaniment, variable speed and key, loops, metronome and practice records.
- [ ] 180. **Home Medication Reminder**: Manage medicines, dosages, reminders, inventory and medication records, and support multi-person files.
- [ ] 181. **Old Mobile Phone Information Screen**: Make a full-screen web signage that displays time, weather, schedule, countdown and remote refresh.
- [ ] 182. **Offline Translation Thesaurus Query**: Import thesaurus files to realize local word search, example sentences, favorites and recent queries.
- [ ] 183. **Home Equipment Inventory**: Record equipment models, room locations, purchase dates, manuals, and maintenance notes with search and reminder views.
- [ ] 184. **Personal Document Full-Text Indexer**: The system indexes local document content, providing search, highlighting, tagging, and privacy protection instructions.
- [ ] 185. **Home Energy Consumption Recorder**: Input electricity meter/water meter/gas readings, display usage trends, cost estimates and abnormal reminders.

- [ ] 471. **Raspberry Pi Home Dashboard**: The system locally displays weather, calendar and countdown to get off work, and supports offline caching and night mode.
- [ ] 472. **USB Device Hot Plug Log**: Record insertion and removal events, device identification and driver prompts to facilitate troubleshooting.
- [ ] 473. **Room Layout Inventory Map**: Place household equipment on a simple floor plan, attach item details, filter by room, and export an inventory sheet.
- [ ] 474. **Offline Map Points of Interest Book**: Import GPX and points of interest, browse and annotate offline, suitable for outdoor use without network.
- [ ] 475. **Sensor Simulator Kit**: Simulate temperature, humidity and door sensor readings and pushes them to local MQTT for automated debugging.
- [ ] 476. **Edge Log Ring Buffer**: Rolling storage of critical logs on resource-constrained devices, supporting export and water level alarms.
- [ ] 477. **Local Priority Note Conflict Demonstration**: Edit the same note offline at both ends, demonstrating conflict marking and merging strategies.
- [ ] 478. **Camera Scheduled Snapshot Archiving**: Save local snapshots according to plan, retention days policy and thumbnail browsing.
- [ ] 479. **Bluetooth Beacon Proximity Demo**: Simulate Bluetooth beacon proximity, trigger a check-in event, record a timeline, and display device battery usage.
- [ ] 480. **Household Energy Consumption Socket Simulation Board**: Simulate multi-channel socket power curves, sets threshold alarms and daily usage summary.
- [ ] 481. **Offline QR Code Scanning Gun Web**: The camera scans the QR code to enter the inventory, and the offline queue is synchronized after being connected to the Internet.
- [ ] 482. **Embedded OTA Status Panel**: Display device firmware version, upgrade batch and failed retries (simulated device group).
- [ ] 483. **Local Media Photo Album Machine**: Raspberry Pi photo frame mode rotates local photo albums, supports weather subtitles and remote delivery switch.
- [ ] 484. **Text Format Debugging Workbench**: Compare line endings, encodings, delimiters, and indentation in local text files, preview conversions, and export corrected copies.
- [ ] 485. **Edge Rule Engine Playground**: Edit if-this-then-that rules, trigger simulated events locally, and record an audit trail.

## 16. Organization and Recordkeeping Tools (30 topics)
> Practice areas: structured records, search, printable layouts, reusable templates.

- [ ] 186. **Household Storage Label Designer**: Design printable labels with room names, item lists, colors, and QR text, preview label sheets, and export PDF.
- [ ] 187. **Recipe Variation Notebook**: Save recipe variations, ingredient substitutions, preparation notes, and photos, compare versions, and export a printable recipe card.
- [ ] 188. **Travel Packing Checklist Builder**: Create packing lists by trip type, assign bags, mark packed items, reuse templates, and print a compact checklist.
- [ ] 189. **Personal Keepsake Archive**: Catalog keepsakes with photos, dates, stories, tags, and storage locations, then browse a timeline and export an album.
- [ ] 190. **Stationery Collection Planner**: Track stationery items, quantities, locations, favorite combinations, and restocking notes with search and a compact dashboard.
- [ ] 191. **Printable Planner Page Designer**: Arrange weekly planner blocks, notes, and checklists on a page, choose typography, preview margins, and export PDF.
- [ ] 192. **Purchase Receipt Organizer**: Import receipt photos and manually entered details, group purchases by shop and month, search notes, and export a CSV summary.
- [ ] 193. **Neighborhood Event Scrapbook**: Record attended events, dates, photos, participants, and reflections, then create a searchable timeline and printable highlights.
- [ ] 194. **Craft Material Inventory**: Track craft materials, colors, quantities, storage bins, and project assignments, with low-stock reminders and CSV export.
- [ ] 195. **Project Reference Card Library**: Store concise reference cards with code snippets, diagrams, tags, and revision notes, then search and print selected cards.
- [ ] 196. **Personal Decision Journal**: Record choices, alternatives, expected outcomes, and later reflections, compare outcomes, and export periodic reviews.
- [ ] 197. **Room Decoration Mood Board**: Arrange images, color palettes, measurements, and furniture notes on a board, compare layouts, and export a presentation image.
- [ ] 198. **Community Borrowing Ledger**: Record shared items, borrowers, pickup and return dates, condition notes, and reminders with a searchable lending view.
- [ ] 199. **Personal Paperwork Checklist**: Track documents needed for routine errands, add deadlines and completion notes, reuse checklist templates, and print selected lists.
- [ ] 200. **Creative Session Notes Organizer**: Record creative sessions, ideas, materials, and next actions, filter by project, and export a weekly progress notebook.

- [ ] 486. **Local Folder Tag Notebook**: Attach descriptive tags and notes to local folder paths, group related folders, find recent entries, and export a catalog.
- [ ] 487. **Collection Exhibit Planner**: Arrange selected collection items into exhibits, add captions and display positions, preview a layout, and print an exhibit guide.
- [ ] 488. **Weekend Task Shuffle Board**: Organize household tasks by time and effort, shuffle a balanced weekend plan, mark completion, and reuse successful plans.
- [ ] 489. **Presentation Rehearsal Log**: Record rehearsal duration, slide notes, speaking reminders, and feedback, compare sessions, and export a revision checklist.
- [ ] 490. **Photo Print Order Planner**: Select local photos, assign print sizes and quantities, preview crop choices, estimate paper use, and export an order sheet.
- [ ] 491. **Celebration Budget Worksheet**: Plan decorations, food, venue supplies, and shared costs, compare estimates with actual spending, and export a budget sheet.
- [ ] 492. **Reading Discussion Card Builder**: Create discussion cards from book notes, group questions by chapter, mark reviewed cards, and export a printable meeting pack.
- [ ] 493. **Workshop Supply Checklist**: Plan materials by activity and participant count, record packed quantities, mark shortages, and export preparation sheets.
- [ ] 494. **Everyday Repair Notes Library**: Record household repair notes, parts, before-and-after photos, costs, and follow-up dates, with tags and search.
- [ ] 495. **Local Text Template Catalog**: Organize reusable text templates with placeholders, preview filled examples, track revisions, and export selected template sets.
- [ ] 496. **Personal Milestone Photo Wall**: Arrange photos and notes around dated milestones, filter by theme, adjust the layout, and export a poster.
- [ ] 497. **Club Attendance Summary Desk**: Import club attendance sheets, group sessions by month, show participation totals, and prepare printable member summaries.
- [ ] 498. **Hobby Project Materials Estimator**: Enter project dimensions and material presets, calculate quantities and cost estimates, save scenarios, and export a shopping sheet.
- [ ] 499. **Board Game Score History**: Record players, games, rounds, and scores, display trends and personal bests, and export selected match histories.
- [ ] 500. **Handmade Item Order Notebook**: Track handmade orders, colors, quantities, preparation steps, due dates, and pickup notes with a simple progress board.

## 17. Industry Workbenches and Vertical Apps (40 topics)
> Practice areas: business modeling, form flow, role view, operation closed loop.

- [ ] 201. **Art Studio Booking Desk**: Manage studio rooms, instructors, workshop appointments, arrivals, rescheduling, cancellations, and a daily attendance queue.
- [ ] 202. **Instrument Repair Case Book**: Record instruments, reported defects, repair steps, parts, estimates, and pickup dates, with a searchable service history.
- [ ] 203. **Gym Membership Manager**: Manage membership plans, personal-training sessions, facility check-ins, renewal reminders, and class usage while showing each member's current status.
- [ ] 204. **Small B&B Operation Desk**: Manage room status, reservations, check-in and check-out, cleaning tasks and income statistics, and support viewing available rooms within a date range.
- [ ] 205. **Restaurant Waiting and Reservation Board**: Record table seats, reservations, waiting queues, check-in and seating status, and provide a quick operation view at the front desk.
- [ ] 206. **Coffee Shop Recipe Costizer**: Maintain beverage recipes, ingredient prices, cup sizes and gross profit estimates to help shop owners compare pricing plans.
- [ ] 207. **Maintenance Work Order Dispatching Platform**: Enter repair reports, assign technicians, track door-to-door time, accessories and settlement status, and display pending work orders according to priority.
- [ ] 208. **Housekeeping Service Scheduler**: Manage customers, service items, schedules, order confirmations and service feedback to reduce scheduling conflicts.
- [ ] 209. **Photography Appointment Process Table**: Maintain customer needs, schedules, contract nodes, film selection progress and delivery lists, and display the current stage of each order.
- [ ] 210. **Course Cancellation System for Training Institutions**: Manage students, course packages, class records, leave requests for make-up classes and remaining class reminders, and support class view.
- [ ] 211. **Community Property Repair Report Desk**: Receive repair reports from owners, categorizes them, dispatches work, processing progress and satisfaction, and provide announcements and entrance to frequently asked questions.
- [ ] 212. **Lawyer Case Follow-up Board**: Record clients, case nodes, materials list, court date reminders and fee status, and display the next action by case.
- [ ] 213. **Psychological Consultation Schedule Book**: Manage visitors, counselor schedules, appointment status, return visit reminders and anonymous statistics, and protect the display of sensitive information.
- [ ] 214. **Dental Implant Process Tracking**: Record patient stages, imaging data, surgical schedules, follow-up visits and cost plans, allowing doctors to quickly check the progress.
- [ ] 215. **Used Car Closing Evaluator**: Input vehicle information, inspection items, valuation, maintenance costs and sales status, and generate a summary of the car closing decision.
- [ ] 216. **Wedding Execution List Desk**: Manage the needs of the couple, suppliers, timelines, payment nodes and tasks of the day, and support viewing to-dos by role.
- [ ] 217. **Fresh Food Order Aggregator**: Collect store ordering requirements, inventory, supplier quotes and arrival status, and generate a purchase summary list.
- [ ] 218. **School Bus Route Manager**: Maintain students, sites, routes, boarding and alighting records and anomaly reminders to facilitate scheduling and view daily operations.
- [ ] 219. **Laboratory Sample Transfer Table**: Record sample number, source, processing steps, owner and storage location, and support status tracking and anomaly marking.
- [ ] 220. **Community Activity Volunteer Desk**: Manage activities, positions, registrations, sign-ins and service hours, and generate volunteer participation records.

- [ ] 501. **Catering Kitchen Preparation List**: Generate preparation list according to reservation and menu, complete the check and waste records.
- [ ] 502. **Parcel Sorting Station Dashboard**: Record incoming parcels, sorting-bin assignments, exceptions, processing time, and loss statistics.
- [ ] 503. **Gym Personal Training Class Reservation**: Manage coaching schedules, membership reservations, cancellation rules and class consumption.
- [ ] 504. **B&B Check-out Check List**: Check-out item scores, photos and compensation records are generated to generate the next sale status.
- [ ] 505. **Driving School Subject Progress Board**: Student subject progress, instructor assignment and test appointment reminder.
- [ ] 506. **Laundry Pickup and Delivery Work Order**: Register garments, condition notes, pickup codes, delivery status, and overdue reminders.
- [ ] 507. **Community Book Exchange Cabinet**: Track cabinet capacity, borrowing and returns, overdue reminders, and tag-based lookup for a community book exchange.
- [ ] 508. **Community Repair Report Dispatching Desk**: Classification of residents’ repair reports, dispatch of work, completion of sign-in and return visit of satisfaction.
- [ ] 509. **Exhibition Booth Construction Progress**: Booth tasks, material arrival and acceptance nodes, showing the risk of delay.
- [ ] 510. **Training Program Trial Conversion Board**: Track trial-session appointments, attendance, interest ratings, follow-up tasks, and conversion status.
- [ ] 511. **Farm Picking Reservation Page**: Park time slot capacity, reservation cancellation and weather rescheduling notice.
- [ ] 512. **Studio Schedule Board**: Studio occupancy, equipment borrowing and customer schedule conflict detection.
- [ ] 513. **Car Beauty Construction Order**: Construction project, technician, quality inspection photos and vehicle delivery confirmation.
- [ ] 514. **Shared Office Visitor Registration**: Visitor reservation, QR code sign-in and host confirmation, export daily report.
- [ ] 515. **Board Game Lending Journal**: Track borrowed games, borrowers, return dates, missing pieces, and condition notes, with reminders and a searchable lending history.
- [ ] 516. **Wedding Preparation Task Tree**: Suppliers, node deadlines and payment node reminders.
- [ ] 517. **Scenic Area Volunteer Schedule**: Job requirements, volunteer skill matching and check-in time statistics.
- [ ] 518. **Campus Lost and Found Desk**: Registration of lost and found items, matching suggestions and verification of claims.
- [ ] 519. **Coffee Bean Roasting Batch Book**: Batch parameters, cupping notes and cup scoring trends (process management).
- [ ] 520. **Warehouse Condition Log**: Record room temperature and humidity samples, annotate storage areas, display trends, and attach inspection notes and follow-up tasks.

## 18. Team Knowledge and Internal Tools (40 topics)
> Practice areas: knowledge management, process collaboration, permission awareness, retrievable information.

- [ ] 221. **Internal SOP Manager**: Maintain process documents, applicable roles, versions, review status, and expiration reminders so the team can find the latest approved procedure.
- [ ] 222. **Newcomer Onboarding Task Package**: Generate onboarding checklists, data links, mentor arrangements and completion progress by position, and support HR to check batch status.
- [ ] 223. **Team Terminology Dictionary**: Include business terms, abbreviations, examples and owners, and support search, pending entries and change history.
- [ ] 224. **Meeting Room Resource Booking**: Manage meeting rooms, equipment, booking conflicts, cancellations and usage statistics, providing a timeline view of the day.
- [ ] 225. **Internal Q&A Knowledge Base**: Let team members submit questions and answers, apply tags, accept solutions, flag stale content, and rank frequently viewed entries.
- [ ] 226. **Customer Handover Manual**: Organize customer background, contacts, risk points, current matters and historical communications to help the person taking over quickly understand the status.
- [ ] 227. **Team Review Database**: Record project reviews, problems, improvement items, owners and follow-up status, and support review of experiences by topic.
- [ ] 228. **Internal Training Registration Desk**: Publish courses, collect registrations, sign-ins, feedback and certificate status, and display training completion rates.
- [ ] 229. **Shared Equipment Borrowing System**: Manage equipment inventory, loan returns, damage records and reservation queues to avoid loss of verbal borrowing.
- [ ] 230. **Team OKR Progress Board**: Maintain goals, key results, owners, confidence values, and progress updates, and generate weekly summaries.
- [ ] 231. **Job Responsibility Map**: Display positions, responsibilities, collaboration objects and common documents to help newcomers understand the organizational division of labor.
- [ ] 232. **Internal Announcement Confirmation Desk**: Publish announcements, collect reading confirmations, track unread people and remind, suitable for important system notifications.
- [ ] 233. **Team Duty Dashboard**: Configure duty roles, members, shifts, holidays and reminders to display the schedule for this week and next week.
- [ ] 234. **Problem Escalation Path Assistant**: The system recommends the owner, response time limit, escalation conditions and processing records according to the problem type to reduce the cost of finding people.
- [ ] 235. **Project Data Archiver**: Organize documents, links, deliverables, archive status and owner by project, supporting unified handover after delivery.
- [ ] 236. **Internal Requirements Collection Box**: Employees submit tool requirements, pain points, impact areas, and votes, which the Product Owner can categorize and prioritize.
- [ ] 237. **Cross-team Dependency Tracking Board**: Record dependencies, contacts, blocking reasons, commitment time and risk status, suitable for daily review by project managers.
- [ ] 238. **System Change Comparator**: Upload two versions of the system text, mark changes in terms, affected positions, and issues to be confirmed, and output a summary of the changes.
- [ ] 239. **Team Skills Matrix**: Maintain member skills, proficiency, project experience and learning plans to help with shift scheduling and training planning.
- [ ] 240. **Internal Tool Directory**: Register tool entrance, owner, applicable scenarios, permission application and fault contact, support search by keywords.

- [ ] 521. **Decision Recording ADR Wall**: Authors architectural decisions, context and consequences, supporting state and associated services.
- [ ] 522. **30-day Checklist for Newbies**: Onboarding tasks by role, mentor confirmation and progress meter.
- [ ] 523. **Glossary Builder**: Team term definitions, aliases and banned words, change subscription notifications.
- [ ] 524. **Meeting Cost Calculator**: Estimate meeting cost from participant roles and duration, show the assumptions, and suggest ways to shorten the meeting.
- [ ] 525. **Internal System Navigation Directory**: Register internal system entrance, owner and permission description, support search.
- [ ] 526. **RFC Comment Workflow**: Publish RFCs, section comments, upvotes, and merged resolutions.
- [ ] 527. **Fault Drill Script Library**: Drill scenarios, steps, observation indicators and review templates.
- [ ] 528. **Anonymous Team Pulse Survey**: Collect periodic anonymous ratings and topic tags, then show aggregate trends without exposing individuals.
- [ ] 529. **Skills Internal Sharing Appointment**: Share topics, time and replay links, and count registrations and feedback.
- [ ] 530. **Office Equipment Loan Desk**: Equipment inventory, loan and damage records, overdue reminders.
- [ ] 531. **Conference Room Equipment Failure Report for Repair**: Repair report, handler and deactivation announcement, associated meeting conflict prompts.
- [ ] 532. **Cross-Team Dependency Registry**: Document service dependencies, contacts, SLA expectations, and change-notification preferences.
- [ ] 533. **Publish the Duty Week Manual**: Duty week responsibilities, contact information and checklist, handover confirmation.
- [ ] 534. **Collaborative Interview Question Library**: Maintain interview questions, evaluation criteria, and usage history to reduce short-term repetition across interviewers.
- [ ] 535. **Internal FAQ Voting Sorting**: FAQ submission, voting to the top and expiration cleanup.
- [ ] 536. **Weekly Report Aggregation Reader**: Pull weekly report entries by team, tag filtering and highlight excerpts.
- [ ] 537. **OKR Review Meeting Minutes Board**: Record goal progress, changes in confidence, blocking decisions and assumptions for the next cycle on a periodic basis, and export review minutes.
- [ ] 538. **Permission Handover Checklist**: System permission recovery list and double confirmation when a person leaves office.
- [ ] 539. **Internal Technology Radar**: Maintain Adopt, Experiment, Evaluate, and Hold entries with votes, comments, ownership, and review dates.
- [ ] 540. **Silent Agenda Board in Conference Room**: Attach the agenda and reference links before a meeting, then track progress and decisions during the session.

## 19. Data Operations and Quality Governance (40 topics)
> Practice areas: data import, cleaning, rule verification, interpretable reports.

- [ ] 241. **CSV Field Mapping Wizard**: Import CSVs from different sources, manually match fields, preview results, save mapping templates, and export standard data.
- [ ] 242. **Data Quality Inspection Platform**: Configure required, unique, range and format rules, and display error samples and repair progress after importing data.
- [ ] 243. **Duplicate Customer Merger Assistant**: The system identifies suspected duplicate customers, displays difference fields, merge suggestions and manual confirmation results, and retains merge records.
- [ ] 244. **Indicator Caliber Manager**: Maintain business indicator definitions, calculation calibers, owners and change history, and reduces team report caliber inconsistencies.
- [ ] 245. **Funnel Conversion Analyzer**: Import event samples, configure funnel steps, and display conversion rates, churn nodes, and group comparisons.
- [ ] 246. **A/B Experiment Results Dashboard**: Enter the experimental group, indicators, sample size and results to show whether the preset goals and conclusion records are achieved.
- [ ] 247. **Data Import Error Inbox**: Receive import failure records, aggregate them by error type, assigns handlers, and mark retry status.
- [ ] 248. **Operation Activity Attribution Table**: Record activities, channels, costs, leads and conversion results to help operations compare input and output.
- [ ] 249. **Retention Cohort Dashboard**: Import user activity data, display retention curves and key date annotations by registration batch.
- [ ] 250. **Abnormal Order Detection Platform**: Import order samples and mark abnormalities according to amount, frequency, address and refund behavior for manual review.
- [ ] 251. **Tag Rule Debugger**: Configure user tag rules and display hit reasons and miss conditions after inputting sample users.
- [ ] 252. **Buried Point Acceptance List**: Maintain pages, events, attributes, owners and acceptance status, and support viewing buried point coverage by version.
- [ ] 253. **Report Subscription Center**: Manage reports, subscribers, sending frequency and recent sending status, and provide failed retry records.
- [ ] 254. **Data Dictionary Browser**: Maintain field names, meanings, enumeration values, sources and examples, support search and recent updates.
- [ ] 255. **Operation List Grouper**: Filter the user list according to conditions, estimate the number of people, save the groups and export the delivery list.
- [ ] 256. **Inventory Turn Analyzer**: Import inventory and sales samples, calculate turnover days, slow-moving items and replenishment recommendations.
- [ ] 257. **Channel Lead Quality Score**: Import leads from different channels, score them based on completeness, follow-up results and transaction status, and display channel rankings.
- [ ] 258. **Refund Reason Analysis Desk**: Summarize refund records, reasons, products and customer service notes to display high-frequency issues and trend changes.
- [ ] 259. **Data Masking Previewer**: Upload sample data, choose masking rules, and preview transformations for names, phone numbers, email addresses, and other sensitive fields.
- [ ] 260. **Metric Incident Review Log**: Record anomalous metrics, impact, investigation steps, root causes, and follow-up actions in a searchable review log.

- [ ] 541. **Simple Diagram of Indicator Lineage**: Maintain the lineage of indicators to table fields and search for downstream effects.
- [ ] 542. **Data Quality Rule Sandbox**: Configure integrity and uniqueness rules, run the sample set and display the violating lines.
- [ ] 543. **Dimension Degradation Detection**: Monitor the sudden increase or decrease in enumerated dimensions and triggers alarm samples.
- [ ] 544. **Report Caliber Change Log**: Record indicator definition changes, effective versions and notification lists.
- [ ] 545. **Buried Event Dictionary**: Event name, attributes, trigger page and owner, support for abandonment mark.
- [ ] 546. **Data Request SLA Board**: Track intake, queue time, ownership, and delivery performance for internal data requests against an SLA.
- [ ] 547. **Illustration Asset Version Ledger**: Maintain versions of illustration files, descriptions, tags, and change notes, compare revisions, and export a selected collection.
- [ ] 548. **Null Value Rate Trend Monitoring**: Key fields Null value rate daily trend and threshold alarm.
- [ ] 549. **Duplicate Primary Key Hunter**: Scan the imported table for duplicate keys and output samples and repair suggestions.
- [ ] 550. **Data Dictionary Review Flow**: Field Definition Proposal, Comment and Approval Release.
- [ ] 551. **Cross-system Reconciliation Difference Table**: Counting and summarizing differences on both sides, positioning and closing status.
- [ ] 552. **Tag Coverage Dashboard**: List of user or content tag coverage and missing items.
- [ ] 553. **Experimental Traffic Distribution Verification**: Check whether the distribution ratio deviates from the configuration and output an alarm.
- [ ] 554. **Data Retention Policy Execution Table**: Table-level retention days, last cleanup, and next schedule.
- [ ] 555. **CSV Schema Drift Detection**: Compare historical upload schemas and mark new or missing columns.
- [ ] 556. **Audience List Deduplication and Merge**: Import an audience list, identify likely duplicates using configurable rules, preview proposed merges, and require manual confirmation.
- [ ] 557. **Funnel Step Configurator**: The system visually configure event steps and windows, and preview conversions.
- [ ] 558. **Data Alarm Acknowledgment Desk**: Alarm distribution, acknowledgment, processing notes and recurrence marks.
- [ ] 559. **Metric Anomaly Explanation Notes**: Capture anomaly conclusions and chart snapshots as searchable notes with links to supporting evidence.
- [ ] 560. **Permission Row-level Policy Directory**: Define row-level filtering rules for datasets, document the applicable roles, and provide a searchable policy directory.

## 20. Creator Business and Community Operations (40 topics)
> Practice areas: content planning, fan operation, commercialization process, feedback closed loop.

- [ ] 261. **Creator Topic Pool**: Collect inspiration, platform, target audience, asset status and release time to support progress from idea to release.
- [ ] 262. **Content Performance Review Platform**: Input multi-platform playback, interaction, conversion and notes to display popular content features and review conclusions.
- [ ] 263. **Sponsorship Cooperation Manager**: Track brands, quotes, deliverables, contract nodes, payments and reviews to avoid missing out on cooperation.
- [ ] 264. **Community Events Calendar**: Manage live broadcasts, check-ins, draws, sharing sessions and registration status, and display upcoming community events.
- [ ] 265. **Fan Question Collection Box**: Collect questions from comments and private messages, cluster them by topic, track reply status, and turn recurring themes into an FAQ.
- [ ] 266. **E-book Sales Backend**: Manage books, orders, discount codes, download permissions and refund status, and display sales trends.
- [ ] 267. **Course Chapter Publisher**: Maintain course chapters, materials, publishing status, student feedback and update plans to help creators deliver at a pace.
- [ ] 268. **Live Broadcast Process Prompt Board**: Prepare live broadcast links, words, product links, interactive reminders and review records, and support advancement by time.
- [ ] 269. **Member Content Permission Table**: Manage membership levels, content packages, expiration times and access records to facilitate checking whether the rights and interests are correct.
- [ ] 270. **Podcast Program Schedule Table**: Record guests, topics, recording time, editing status, release channels and promotional materials.
- [ ] 271. **Short Video Script Workbench**: Split the opening, main body, transition and ending, manage materials, shooting status and version comparison.
- [ ] 272. **Social Check-in Challenger**: Create challenges, member registration, daily check-ins, make-up rules and rankings, and output activity reviews.
- [ ] 273. **Product Crowdfunding Progress Page**: Display the target amount, supporters, levels, production nodes and risk updates for public follow-up by the project party.
- [ ] 274. **Knowledge Planet Content Index**: Organize posts, topics, essences, authors and update times to help members quickly find old content.
- [ ] 275. **Creator Financial Summary**: Record platform income, sponsorship, costs, taxes and settlement status, and generate a monthly income view.
- [ ] 276. **Brand Material Asset Library**: Manage logos, covers, fonts, templates and usage instructions, support downloads and version tags.
- [ ] 277. **Comment Lottery Tool**: Import the comment list, set filtering rules, lottery quota and winning records, and generate a public results page.
- [ ] 278. **Joint Project Collaboration Board**: Record partners, tasks, deliverables, review opinions and release time, and display the to-dos of both parties.
- [ ] 279. **Content Redistribution Assistant**: Split a piece of content into multi-platform publishing tasks, recording the title, cover, publishing time and link.
- [ ] 280. **Fan Growth Path Map**: Design the touch points, tasks and rights of new fans, active fans, and paying fans, and track conversions at each stage.

- [ ] 561. **Content Topic Selection Ballot Box**: Fans vote for topics, showing the trend of votes and the final schedule.
- [ ] 562. **Member Renewal Redemption Sequence**: Configure reminder copywriting and channels before expiration, and track redemption results.
- [ ] 563. **Peripheral Product Inventory Board**: SKU inventory, pre-sale and replenishment reminders, associated promotion nodes.
- [ ] 564. **Community Welcome Flow Arrangement**: New member welcome steps, tasks and reward marks.
- [ ] 565. **Co-branded Content Rights Table**: Record the number of exposures, materials and acceptance status of the partner.
- [ ] 566. **Live Broadcast Gift Thank You List**: Import the reward list to generate thank you scripts and pinned lists.
- [ ] 567. **Column Update Commitment Board**: Show readers the update frequency commitment and actual delivery.
- [ ] 568. **Fan Submission Review Desk**: Submission queue, review comments and adoption status.
- [ ] 569. **Offline Meeting Registration Verification**: Registration, sign-in code and material collection records.
- [ ] 570. **Content Licensing Library**: External licensing scope, period and renewal reminder.
- [ ] 571. **Classified Handling of Community Violations**: Rule levels, handling actions and appeal records.
- [ ] 572. **Coursework Peer Evaluation Board**: Students’ mutual evaluation tasks, scoring rubrics and display of excellent assignments.
- [ ] 573. **Acceptance of Brand Cooperation Materials**: List of deliverables, revision rounds and final confirmation.
- [ ] 574. **Multi-platform Fan Growth Experiment**: Record experimental hypotheses, actions and growth results.
- [ ] 575. **Knowledge Base Paid Chapter Access Control**: Chapter permissions, trial reading and unlocking records (demo).
- [ ] 576. **Creator Tax Folder**: Collect invoices and income voucher lists (data management, non-tax calculation).
- [ ] 577. **Activity Volunteer Recruitment Page**: Position, registration review and shift confirmation.
- [ ] 578. **Content Calendar Conflict Detection**: Multiple accounts publish calendars to detect collisions and empty windows.
- [ ] 579. **Fan Badge Achievement System**: Define badge conditions, issuance records and display wall.
- [ ] 580. **Podcast Ad Insertion Schedule**: Bind advertising slots to customers and podcast episodes, track availability, and prevent overselling.

## 21. Operations, Testing, and Delivery Assurance (40 topics)
> Practice areas: operation observation, quality inspection, release process, fault recovery.

- [ ] 281. **Scheduled Task Result Panel**: Import job execution records, show the latest result and duration, filter failures, and compare trends across recurring jobs.
- [ ] 282. **Interface Smoke Test Bench**: Maintain interfaces, request samples, expected results and recent execution status, suitable for quick verification before release.
- [ ] 283. **Release Window Calendar**: Record version, owner, freezing period, release time and rollback contact to avoid conflicting releases.
- [ ] 284. **Rollback Drill Checklist**: Maintain the system, rollback steps, verification points, drill records and risk items to help the team drill regularly.
- [ ] 285. **Configuration Change Approval Desk**: Submit configuration items, impact scope, approvers, release time and verification results, and keep change records.
- [ ] 286. **Alert Noise Reduction Rule Builder**: Define alert triggers, silence windows, grouping rules, and routing behavior, then preview which alerts would be merged.
- [ ] 287. **Fault Timeline Recorder**: Record time points, events, owners and decisions during fault handling, and export the review timeline afterwards.
- [ ] 288. **Dependent Service Status Wall**: Display third-party services, recent status, scope of impact, and alternatives for customer service and R&D to view.
- [ ] 289. **Test Case Review Desk**: Manage requirements, test points, use cases, review comments and execution status to help QA track coverage.
- [ ] 290. **Defect Lifecycle Dashboard**: Record defects, severity, owner, fixed version and verification status, and display backlog trends.
- [ ] 291. **Post-release Inspection Assistant**: Generate inspection items, owners, results and anomaly notes based on versions, and support unified confirmation after release.
- [ ] 292. **Log Sample Annotator**: Import log fragments, annotate levels, modules, error types and handling suggestions, and accumulate troubleshooting data.
- [ ] 293. **Capacity Estimator**: Enter user counts, request volume, data growth, and retention periods to estimate capacity trends and highlight risks.
- [ ] 294. **Change Impact Diagram**: Maintain services, interfaces, queues and dependencies, and display the possible impact scope after entering changes.
- [ ] 295. **Environment Consistency Checker**: Compare configuration items and versions of development, testing, and production, and mark differences and items to be confirmed.
- [ ] 296. **Canary Release Monitoring Board**: Track canary cohorts, traffic percentages, metric thresholds, pause conditions, and the result of each rollout stage.
- [ ] 297. **Data Backup Acceptance Form**: Manage backup tasks, latest success time, recovery drills and exception records, and remind backups that have not been verified for a long time.
- [ ] 298. **Documentation Correction Tracker**: Register document issues, affected pages, owners, deadlines, and review results, and display overdue corrections.
- [ ] 299. **Automated Job Runbook**: Record scheduled jobs, recent executions, duration, failure reasons, and a controlled manual rerun action for operators.
- [ ] 300. **Release Risk Assessment Table**: Generate a release risk summary based on functional scope, data impact, dependencies, rollback difficulty, and verification plan scores.

---

- [ ] 581. **Canary Watch List**: Record canary indicators, observation windows and promotion or rollback decisions.
- [ ] 582. **Synthetic Monitoring Script Library**: Manage critical path synthetic detection scripts, frequency and failure screenshots.
- [ ] 583. **Release Notes Assembler**: Assemble draft release notes from PR labels, group changes by type, and attach concise risk warnings.
- [ ] 584. **Disaster Recovery Switching Checklist**: Switching steps, verification points and communication templates, supporting drill mode.
- [ ] 585. **Hot Configuration Update Audit**: Record each hot configuration update, operator, validation result, and rollback point.
- [ ] 586. **Test Environment Reservation Calendar**: Reserve shared test environments, detect conflicts, show current ownership, and remind teams to release unused reservations.
- [ ] 587. **Defect Clustering Dashboard**: Cluster defects by module and error signature to display hot spots.
- [ ] 588. **Page Render Baseline Comparator**: Import local page-render timing samples, compare percentiles across versions, highlight slower pages, and export a performance report.
- [ ] 589. **Dependency Service Drill Switch**: Simulate dependency fault switch and record the drill results.
- [ ] 590. **Release Window Conflict Radar**: Visualize release windows across teams and highlight overlapping dependencies and schedule risks.
- [ ] 591. **Log Sampling Policy Configuration**: Configure module sampling rate and retention period, and estimate storage usage.
- [ ] 592. **Alarm Routing Simulator**: Enter alarm samples, preview notifications to people or groups, and upgrade chains.
- [ ] 593. **Artifact Promotion Pipeline**: Show an artifact's promotion from development through staging to production, including status, evidence, and approval records.
- [ ] 594. **One-Click Rollback Drill**: Run a rollback playbook in dry-run mode against a staging environment and report the duration and result of each step.
- [ ] 595. **Test Data Reset Tool**: Reset environment seed data with one click, record version and executor.
- [ ] 596. **Capacity Water Level Weekly Report**: Summarize CPU and storage water levels and growth forecasts (sample) to generate a weekly report.
- [ ] 597. **Change Freeze Calendar**: Maintain change-freeze windows and exception approvals, and warn when a planned release conflicts with a freeze.
- [ ] 598. **Smoke Use Case Priority Wall**: Smoke set ranking, recent failures and owners.
- [ ] 599. **Release Stage Progress Panel**: Display deliverables moving through draft, review, staging, and completion, with owner notes, timestamps, and stage summaries.
- [ ] 600. **Deliverable Acceptance Checker**: Validate evidence links against an acceptance checklist, flag missing proof, and generate a release decision report.

## Progress

- Total topics: **600**
- Completed: **0**
- In progress: **0**

## Notes

- Difficulty varies widely, so start with the idea that interests you most; there is no need to work from 1 to 600 in order.
- Rebuild an idea with a **different technology stack** for comparison, such as implementing Snake with Canvas, WebGL, and a terminal UI.
- After completion, add a README under `done/<number>-<title>/` describing what you learned.
