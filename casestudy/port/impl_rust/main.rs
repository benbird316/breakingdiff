// 移植层案例：Rust 实现（零 crate —— 自带只认本 schema 的最小 JSON 解析器）。
//
// 仓库纪律是「无第三方依赖」。claims.json 的结构足够小，所以这里手写解析
// 而不是引 serde_json：**契约小的时候，零依赖是选项**——这本身就是教学点。
//
// 用法：
//   rustc -O main.rs -o port_rust.exe
//   .\port_rust.exe --spec ../../claims.json
//   .\port_rust.exe --spec ../../claims.json --mutant boundary   # 错移植：ge 写成 gt
use std::env;
use std::fs;
use std::process::exit;

#[derive(Debug, Clone)]
enum Value {
    Null,
    Bool(bool),
    Num(i64),
    Str(String),
    Arr(Vec<Value>),
    Obj(Vec<(String, Value)>),
}

struct Parser<'a> {
    s: &'a [u8],
    i: usize,
}

impl<'a> Parser<'a> {
    fn new(s: &'a str) -> Self {
        Parser { s: s.as_bytes(), i: 0 }
    }

    fn ws(&mut self) {
        while self.i < self.s.len() && (self.s[self.i] as char).is_ascii_whitespace() {
            self.i += 1;
        }
    }

    fn parse(&mut self) -> Value {
        self.ws();
        let v = self.parse_value();
        self.ws();
        v
    }

    fn parse_value(&mut self) -> Value {
        self.ws();
        match self.s[self.i] {
            b'{' => self.parse_object(),
            b'[' => self.parse_array(),
            b'"' => Value::Str(self.parse_string()),
            b't' => {
                self.expect("true");
                Value::Bool(true)
            }
            b'f' => {
                self.expect("false");
                Value::Bool(false)
            }
            b'n' => {
                self.expect("null");
                Value::Null
            }
            _ => self.parse_number(),
        }
    }

    fn expect(&mut self, lit: &str) {
        if self.s.len() < self.i + lit.len() || &self.s[self.i..self.i + lit.len()] != lit.as_bytes() {
            exit_err(&format!("expected literal {lit} at {}", self.i));
        }
        self.i += lit.len();
    }

    fn parse_number(&mut self) -> Value {
        let start = self.i;
        if self.i < self.s.len() && self.s[self.i] == b'-' {
            self.i += 1;
        }
        while self.i < self.s.len() && self.s[self.i].is_ascii_digit() {
            self.i += 1;
        }
        let text = std::str::from_utf8(&self.s[start..self.i]).unwrap_or("");
        match text.parse::<i64>() {
            Ok(n) => Value::Num(n),
            Err(_) => exit_err(&format!("bad number {text:?}")),
        }
    }

    fn parse_string(&mut self) -> String {
        self.i += 1; // opening quote
        let mut out = String::new();
        while self.i < self.s.len() {
            match self.s[self.i] {
                b'"' => {
                    self.i += 1;
                    return out;
                }
                b'\\' => {
                    self.i += 1;
                    let esc = self.s[self.i];
                    self.i += 1;
                    match esc {
                        b'"' => out.push('"'),
                        b'\\' => out.push('\\'),
                        b'/' => out.push('/'),
                        b'n' => out.push('\n'),
                        b't' => out.push('\t'),
                        b'r' => out.push('\r'),
                        _ => exit_err("unsupported escape"),
                    }
                }
                _ => {
                    let start = self.i;
                    while self.i < self.s.len() && self.s[self.i] != b'"' && self.s[self.i] != b'\\' {
                        self.i += 1;
                    }
                    out.push_str(std::str::from_utf8(&self.s[start..self.i]).unwrap_or(""));
                }
            }
        }
        exit_err("unterminated string")
    }

    fn parse_array(&mut self) -> Value {
        self.i += 1;
        let mut items = Vec::new();
        loop {
            self.ws();
            if self.i < self.s.len() && self.s[self.i] == b']' {
                self.i += 1;
                return Value::Arr(items);
            }
            items.push(self.parse_value());
            self.ws();
            if self.i < self.s.len() && self.s[self.i] == b',' {
                self.i += 1;
            }
        }
    }

    fn parse_object(&mut self) -> Value {
        self.i += 1;
        let mut fields = Vec::new();
        loop {
            self.ws();
            if self.i < self.s.len() && self.s[self.i] == b'}' {
                self.i += 1;
                return Value::Obj(fields);
            }
            let key = self.parse_string();
            self.ws();
            if self.i >= self.s.len() || self.s[self.i] != b':' {
                exit_err("expected ':'");
            }
            self.i += 1;
            let value = self.parse_value();
            fields.push((key, value));
            self.ws();
            if self.i < self.s.len() && self.s[self.i] == b',' {
                self.i += 1;
            }
        }
    }
}

fn exit_err(msg: &str) -> ! {
    eprintln!("{msg}");
    exit(2)
}

fn get<'a>(v: &'a Value, key: &str) -> &'a Value {
    match v {
        Value::Obj(fields) => fields
            .iter()
            .find(|(k, _)| k == key)
            .map(|(_, v)| v)
            .unwrap_or_else(|| exit_err(&format!("missing key {key}"))),
        _ => exit_err(&format!("expected object for key {key}")),
    }
}

fn as_i64(v: &Value) -> i64 {
    match v {
        Value::Num(n) => *n,
        _ => exit_err("expected number"),
    }
}

fn as_str(v: &Value) -> &str {
    match v {
        Value::Str(s) => s,
        _ => exit_err("expected string"),
    }
}

fn as_arr(v: &Value) -> &[Value] {
    match v {
        Value::Arr(items) => items,
        _ => exit_err("expected array"),
    }
}

fn as_bool(v: &Value) -> bool {
    match v {
        Value::Bool(b) => *b,
        _ => exit_err("expected bool"),
    }
}

const MAX_WITNESS: usize = 8;

fn eval_op(op: &Value, point: &Value, mutate_boundary: bool) -> bool {
    let kind = as_str(get(op, "op"));
    if kind == "always" {
        return true;
    }
    let x = as_i64(get(point, as_str(get(op, "field"))));
    match kind {
        "ge" => {
            let v = as_i64(get(op, "value"));
            // 错移植：边界差一。与 Go 侧同名 mutant，读数可对拍。
            if mutate_boundary {
                x > v
            } else {
                x >= v
            }
        }
        "gt" => x > as_i64(get(op, "value")),
        "band" => as_i64(get(op, "lo")) <= x && x < as_i64(get(op, "hi")),
        other => exit_err(&format!("unknown op {other}")),
    }
}

fn guard(claim: &Value) {
    let name = as_str(get(claim, "name"));
    for test in as_arr(get(claim, "source_tests")) {
        let point = get(test, "point");
        if eval_op(get(claim, "predicate"), point, false) != as_bool(get(test, "expected")) {
            eprintln!("[{name}] source test failed");
            exit(2);
        }
    }
}

fn verdict_key(divergence: i64, dominance: i64, common: i64) -> &'static str {
    if divergence > 0 && dominance == 0 {
        "p_strict_contains_q"
    } else if dominance > 0 && divergence == 0 {
        "q_strict_contains_p"
    } else if divergence > 0 && dominance > 0 {
        "parallel"
    } else if common > 0 {
        "equivalent"
    } else {
        "disjoint"
    }
}

fn main() {
    let args: Vec<String> = env::args().skip(1).collect();
    let mut spec_path = String::from("claims.json");
    let mut mutant = String::new();
    let mut i = 0;
    while i < args.len() {
        match args[i].as_str() {
            "--spec" => {
                spec_path = args[i + 1].clone();
                i += 2;
            }
            "--mutant" => {
                mutant = args[i + 1].clone();
                i += 2;
            }
            other => exit_err(&format!("unknown argument {other}")),
        }
    }
    let mutate = mutant == "boundary";

    let text = match fs::read_to_string(&spec_path) {
        Ok(t) => t,
        Err(e) => exit_err(&format!("read spec: {e}")),
    };
    let spec = Parser::new(&text).parse();
    if as_i64(get(&spec, "schema_version")) != 1 {
        exit_err("unsupported schema_version");
    }

    let domain = as_arr(get(&spec, "domain"));
    let pairs = as_arr(get(&spec, "pairs"));
    let mut results: Vec<String> = Vec::new();
    let mut all_match = true;

    for pair in pairs {
        let p_claim = get(pair, "P");
        let q_claim = get(pair, "Q");
        guard(p_claim);
        guard(q_claim);

        let p_pred = get(p_claim, "predicate");
        let q_pred = get(q_claim, "predicate");
        let p_applies = get(p_claim, "applies");
        let q_applies = get(q_claim, "applies");

        let (mut common, mut divergence, mut dominance, mut neither, mut out_of_domain) =
            (0i64, 0i64, 0i64, 0i64, 0i64);
        let mut dv: Vec<i64> = Vec::new();
        let mut dw: Vec<i64> = Vec::new();

        for point in domain {
            // 域外判定不参与 mutant：错移植只错在判定面。
            if !eval_op(p_applies, point, false) || !eval_op(q_applies, point, false) {
                out_of_domain += 1;
                continue;
            }
            let p = eval_op(p_pred, point, mutate);
            let q = eval_op(q_pred, point, mutate);
            if p && q {
                common += 1;
            } else if p && !q {
                divergence += 1;
                if dv.len() < MAX_WITNESS {
                    dv.push(as_i64(get(point, "n")));
                }
            } else if !p && q {
                dominance += 1;
                if dw.len() < MAX_WITNESS {
                    dw.push(as_i64(get(point, "n")));
                }
            } else {
                neither += 1;
            }
        }

        let verdict = verdict_key(divergence, dominance, common);
        let expect = get(pair, "expect");
        let matches = common == as_i64(get(expect, "common"))
            && divergence == as_i64(get(expect, "divergence"))
            && dominance == as_i64(get(expect, "dominance"))
            && neither == as_i64(get(expect, "neither"))
            && out_of_domain == as_i64(get(expect, "out_of_domain"))
            && verdict == as_str(get(expect, "verdict"));
        all_match &= matches;

        let join = |nums: &[i64]| -> String {
            nums.iter().map(|n| n.to_string()).collect::<Vec<_>>().join(",")
        };
        results.push(format!(
            "{{\"id\":\"{}\",\"common\":{},\"divergence\":{},\"dominance\":{},\"neither\":{},\"out_of_domain\":{},\"verdict\":\"{}\",\"divergence_witness\":[{}],\"dominance_witness\":[{}]}}",
            as_str(get(pair, "id")),
            common,
            divergence,
            dominance,
            neither,
            out_of_domain,
            verdict,
            join(&dv),
            join(&dw)
        ));
    }

    println!(
        "{{\"results\":[{}],\"match_expect\":{}}}",
        results.join(","),
        all_match
    );
    if !all_match {
        exit(1);
    }
}
