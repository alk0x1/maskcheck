# Finding 003 PR preparation

Date: 2026-08-25

Base revision: `53da3ff8c0db359ecb6d4b41f154308c82a89aaf`

Local branch: `fix/json-schema-carriage-return-whitespace`

Local commit: `9cbcbb7`

Proposed commit title: `fix: accept carriage return as JSON whitespace`

No PR was opened and no branch was pushed.

## Diff

```diff
diff --git a/cpp/json_schema_converter.cc b/cpp/json_schema_converter.cc
index 0f3d225..5db360c 100644
--- a/cpp/json_schema_converter.cc
+++ b/cpp/json_schema_converter.cc
@@ -1612,9 +1612,9 @@ void IndentManager::EndIndent() {
 std::string IndentManager::StartSeparator() {
   if (any_whitespace_) {
     if (!max_whitespace_cnt_.has_value()) {
-      return "[ \\n\\t]*";
+      return "[ \\n\\r\\t]*";
     } else {
-      return "[ \\n\\t]{0," + std::to_string(max_whitespace_cnt_.value()) + "}";
+      return "[ \\n\\r\\t]{0," + std::to_string(max_whitespace_cnt_.value()) + "}";
     }
   }
   if (!enable_newline_) {
@@ -1627,9 +1627,9 @@ std::string IndentManager::MiddleSeparator() {
   if (any_whitespace_) {
     std::string whitespace_part;
     if (!max_whitespace_cnt_.has_value()) {
-      whitespace_part = "[ \\n\\t]*";
+      whitespace_part = "[ \\n\\r\\t]*";
     } else {
-      whitespace_part = "[ \\n\\t]{0," + std::to_string(max_whitespace_cnt_.value()) + "}";
+      whitespace_part = "[ \\n\\r\\t]{0," + std::to_string(max_whitespace_cnt_.value()) + "}";
     }
     return whitespace_part + " \"" + separator_ + "\" " + whitespace_part;
   }
@@ -1642,9 +1642,9 @@ std::string IndentManager::MiddleSeparator() {
 std::string IndentManager::EndSeparator() {
   if (any_whitespace_) {
     if (!max_whitespace_cnt_.has_value()) {
-      return "[ \\n\\t]*";
+      return "[ \\n\\r\\t]*";
     } else {
-      return "[ \\n\\t]{0," + std::to_string(max_whitespace_cnt_.value()) + "}";
+      return "[ \\n\\r\\t]{0," + std::to_string(max_whitespace_cnt_.value()) + "}";
     }
   }
   if (!enable_newline_) {
@@ -1656,9 +1656,9 @@ std::string IndentManager::EndSeparator() {
 std::string IndentManager::EmptySeparator() {
   if (any_whitespace_) {
     if (!max_whitespace_cnt_.has_value()) {
-      return "[ \\n\\t]*";
+      return "[ \\n\\r\\t]*";
     } else {
-      return "[ \\n\\t]{0," + std::to_string(max_whitespace_cnt_.value()) + "}";
+      return "[ \\n\\r\\t]{0," + std::to_string(max_whitespace_cnt_.value()) + "}";
     }
   }
   return "\"\"";
@@ -1669,16 +1669,16 @@ std::string IndentManager::NextSeparator(bool is_end) {
     if (is_first_.back() || is_end) {
       is_first_.back() = false;
       if (!max_whitespace_cnt_.has_value()) {
-        return "[ \\n\\t]*";
+        return "[ \\n\\r\\t]*";
       } else {
-        return "[ \\n\\t]{0," + std::to_string(max_whitespace_cnt_.value()) + "}";
+        return "[ \\n\\r\\t]{0," + std::to_string(max_whitespace_cnt_.value()) + "}";
       }
     } else {
       std::string whitespace_part;
       if (!max_whitespace_cnt_.has_value()) {
-        whitespace_part = "[ \\n\\t]*";
+        whitespace_part = "[ \\n\\r\\t]*";
       } else {
-        whitespace_part = "[ \\n\\t]{0," + std::to_string(max_whitespace_cnt_.value()) + "}";
+        whitespace_part = "[ \\n\\r\\t]{0," + std::to_string(max_whitespace_cnt_.value()) + "}";
       }
       return whitespace_part + " \"" + separator_ + "\" " + whitespace_part;
     }
@@ -1987,13 +1987,15 @@ int32_t JSONSchemaConverter::AddSubGrammar(const Grammar& grammar) {
 
 std::string JSONSchemaConverter::GetWhitespacePattern() const {
   if (!max_whitespace_cnt_.has_value()) {
-    return "[ \\n\\t]*";
+    return "[ \\n\\r\\t]*";
   }
-  return "[ \\n\\t]{0," + std::to_string(*max_whitespace_cnt_) + "}";
+  return "[ \\n\\r\\t]{0," + std::to_string(*max_whitespace_cnt_) + "}";
 }
 
 int32_t JSONSchemaConverter::WhitespaceExpression() {
-  std::vector<CharacterClassElement> elements = {{' ', ' '}, {'\n', '\n'}, {'\t', '\t'}};
+  std::vector<CharacterClassElement> elements = {
+      {' ', ' '}, {'\n', '\n'}, {'\r', '\r'}, {'\t', '\t'}
+  };
   if (!max_whitespace_cnt_.has_value()) {
     if (!whitespace_expr_id_.has_value()) {
       whitespace_expr_id_ = builder_.AddCharacterClassStar(elements);
diff --git a/tests/python/test_json_schema_converter.py b/tests/python/test_json_schema_converter.py
index faa1be4..900bb78 100644
--- a/tests/python/test_json_schema_converter.py
+++ b/tests/python/test_json_schema_converter.py
@@ -1062,6 +1062,18 @@ root ::= "{" [ \n\t]* (("\"value\"" [ \n\t]* ":" [ \n\t]* basic_string root_part
         check_schema_with_instance(schema, instance, any_whitespace=True)
 
 
+def test_carriage_return_whitespace():
+    schema = {
+        "type": "object",
+        "properties": {"a": {"type": "string"}},
+        "required": ["a"],
+        "additionalProperties": False,
+    }
+    instances = ['{\r"a":"x"}', '{"a"\r:"x"}', '{"a":\r"x"}', '{"a":"x"\r}', '{\r\n  "a": "x"\r\n}']
+    for instance in instances:
+        check_schema_with_instance(schema, instance, any_whitespace=True)
+
+
 schema__err_message__test_array_schema_error_cases = [
     ({"type": "array", "prefixItems": {"type": "string"}}, "prefixItems must be an array"),
     (
@@ -2958,8 +2970,8 @@ def test_limited_whitespace_cnt():
 basic_string_sub ::= (("\"") | ([^\0-\x1f\"\\\r\n] basic_string_sub) | ("\\" basic_escape basic_string_sub)) (=(basic_string_sub_4 [,}\]:]))
 basic_string ::= (("\"" basic_string_sub)) (=(basic_string_sub_4 "}"))
 root ::= (("{" basic_string_sub_4 "\"key\"" basic_string_sub_4 ":" basic_string_sub_4 basic_string basic_string_sub_4 "}"))
-basic_string_sub_2 ::= ("" | ([ \n\t] basic_string_sub_3))
-basic_string_sub_3 ::= ("" | ([ \n\t]))
+basic_string_sub_2 ::= ("" | ([ \n\r\t] basic_string_sub_3))
+basic_string_sub_3 ::= ("" | ([ \n\r\t]))
 basic_string_sub_4 ::= ((basic_string_sub_2))
 """
     schema = {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]}
@@ -2978,8 +2990,8 @@ def test_limited_whitespace_compile():
 basic_string_sub ::= (("\"") | ([^\0-\x1f\"\\\r\n] basic_string_sub) | ("\\" basic_escape basic_string_sub)) (=(basic_string_sub_4 [,}\]:]))
 basic_string ::= (("\"" basic_string_sub)) (=(basic_string_sub_4 "}"))
 root ::= (("{" basic_string_sub_4 "\"key\"" basic_string_sub_4 ":" basic_string_sub_4 basic_string basic_string_sub_4 "}"))
-basic_string_sub_2 ::= ("" | ([ \n\t] basic_string_sub_3))
-basic_string_sub_3 ::= ("" | ([ \n\t]))
+basic_string_sub_2 ::= ("" | ([ \n\r\t] basic_string_sub_3))
+basic_string_sub_3 ::= ("" | ([ \n\r\t]))
 basic_string_sub_4 ::= ((basic_string_sub_2))
 """
     schema = {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]}
```

## Verification

Before the fix, the new behavioral test failed on the first valid JSON instance containing CR:

```text
FAILED tests/python/test_json_schema_converter.py::test_carriage_return_whitespace
1 failed in 1.32s
```

After the fix, the complete upstream converter suite passed:

```text
519 passed in 12.45s
```

The repository hooks for the two changed files also passed:

```text
black....................................................................Passed
isort....................................................................Passed
clang-format.............................................................Passed
```

## PR description

Fixes [#861](https://github.com/mlc-ai/xgrammar/issues/861) by adding carriage return to both JSON whitespace representations used by the converter and keeping the generated separator patterns consistent with them. The regression test covers CR before an object key, before and after the colon, before the closing brace, and CRLF around an object body.
