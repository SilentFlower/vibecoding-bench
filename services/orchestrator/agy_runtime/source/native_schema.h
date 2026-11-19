/* 字段来自固定执行体的真实Go类型。 */
typedef struct { const char *name; unsigned offset, bytes, kind; } Field;
static const Field fields_0[] = {{"Model",8,4,4},{"InputTokens",16,8,4},{"OutputTokens",24,8,4},{"ThinkingOutputTokens",32,8,4},{"ResponseOutputTokens",40,8,4},{"CacheWriteTokens",48,8,4},{"CacheReadTokens",56,8,4},{"ApiProvider",64,4,4},{"MessageId",72,16,1},{"ResponseHeader",88,8,8},{"ResponseId",96,16,1},{"ProviderAssignedMessageId",112,16,1},{"ServiceTier",128,16,1},{"PromptTokensDetails",144,24,7},{"CacheTokensDetails",168,24,7},{"CandidatesTokensDetails",192,24,7},{"ToolUsePromptTokensDetails",216,24,7}};
#define COUNT_0 (sizeof(fields_0)/sizeof(fields_0[0]))
static const Field fields_1[] = {{"Id",8,16,1},{"Name",24,16,1},{"ArgumentsJson",40,16,1},{"InvalidJsonStr",56,16,1},{"InvalidJsonErr",72,16,1},{"ThoughtSignature",88,16,1},{"ThinkingSignature_base64",104,24,2},{"OriginalArgumentsJson",128,16,1},{"OriginalName",144,16,1},{"FunctionCallParts",160,24,7}};
#define COUNT_1 (sizeof(fields_1)/sizeof(fields_1[0]))
static const Field fields_2[] = {{"MessageId",8,16,1},{"DeltaText",24,16,1},{"DeltaTokens",40,4,4},{"StopReason",44,4,4},{"DeltaToolCalls",48,24,6},{"Usage",72,8,5},{"DeltaRawGeneration",80,16,1},{"DeltaThinking",96,16,1},{"DeltaRawThinking",112,16,1},{"DeltaSignature_base64",128,24,2},{"ThinkingRedacted",152,1,3},{"Latency",160,8,9},{"CitationMetadata",168,8,8},{"SherlogLink",176,16,1},{"TraceId",192,16,1},{"StopMessage",208,16,1},{"ConsumedCredits",224,24,7},{"ResponseModel",248,16,1},{"ProviderAssignedMessageId",264,16,1},{"DeltaCustomExtensions",280,8,8}};
#define COUNT_2 (sizeof(fields_2)/sizeof(fields_2[0]))
/* OAuth使用channelModelResponseStream；Scanner观察点位于栈检查之后，避免栈增长重复进入。 */
static const unsigned long sites[4] = {0xa098532,0x95d1e90,0x89ed91f,0x95f3212};
static const unsigned char expected_0[] = {0x48,0x89,0x9c,0x24,0x88,0x0,0x0,0x0};
static const unsigned char expected_1[] = {0x84,0xc0,0x74,0x7f,0x90,0x48,0x8b,0x54};
static const unsigned char expected_2[] = {0x90,0x48,0x83,0xfb,0x1,0x75,0x7,0xba};
static const unsigned char expected_3[] = {0x48,0x89,0x44,0x24,0x70,0x90,0x48,0x8d};
