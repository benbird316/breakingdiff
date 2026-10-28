// Port-layer case: Go implementation (stdlib encoding/json, zero third-party dependencies).
//
// Reads the same claims.json and independently implements operator evaluation + four quadrants + verdict keys + witness points;
// emits JSON so test_port.py can compare point by point with the Python reference.
//
// Usage:
//   go run main.go -spec ../../claims.json
//   go run main.go -spec ../../claims.json -mutant boundary   # wrong port: ge written as gt
package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
)

type Op struct {
	Op    string `json:"op"`
	Field string `json:"field"`
	Value int    `json:"value"`
	Lo    int    `json:"lo"`
	Hi    int    `json:"hi"`
}

type SourceTest struct {
	Point    map[string]int `json:"point"`
	Expected bool           `json:"expected"`
}

type ClaimSpec struct {
	Name        string       `json:"name"`
	Applies     Op           `json:"applies"`
	Predicate   Op           `json:"predicate"`
	Source      string       `json:"source"`
	Quote       string       `json:"quote"`
	SourceTests []SourceTest `json:"source_tests"`
}

type Expect struct {
	Common             int    `json:"common"`
	Divergence         int    `json:"divergence"`
	Dominance          int    `json:"dominance"`
	Neither            int    `json:"neither"`
	OutOfDomain        int    `json:"out_of_domain"`
	Verdict            string `json:"verdict"`
	DivergenceWitness  []int  `json:"divergence_witness"`
	DominanceWitness   []int  `json:"dominance_witness"`
}

type Pair struct {
	ID     string    `json:"id"`
	P      ClaimSpec `json:"P"`
	Q      ClaimSpec `json:"Q"`
	Expect Expect    `json:"expect"`
}

type Spec struct {
	SchemaVersion int                `json:"schema_version"`
	Domain        []map[string]int   `json:"domain"`
	Pairs         []Pair             `json:"pairs"`
}

type Result struct {
	ID                string `json:"id"`
	Common            int    `json:"common"`
	Divergence        int    `json:"divergence"`
	Dominance         int    `json:"dominance"`
	Neither           int    `json:"neither"`
	OutOfDomain       int    `json:"out_of_domain"`
	Verdict           string `json:"verdict"`
	DivergenceWitness []int  `json:"divergence_witness"`
	DominanceWitness  []int  `json:"dominance_witness"`
}

const maxWitness = 8

func evalOp(op Op, point map[string]int, mutateBoundary bool) bool {
	switch op.Op {
	case "always":
		return true
	case "ge":
		// Wrong port: off-by-one boundary. Deliberately kept at the same evaluation point so it lies dormant like a real bug.
		if mutateBoundary {
			return point[op.Field] > op.Value
		}
		return point[op.Field] >= op.Value
	case "gt":
		return point[op.Field] > op.Value
	case "band":
		return op.Lo <= point[op.Field] && point[op.Field] < op.Hi
	}
	fmt.Fprintf(os.Stderr, "unknown op %q\n", op.Op)
	os.Exit(2)
	return false
}

func guard(c ClaimSpec) {
	for _, t := range c.SourceTests {
		if evalOp(c.Predicate, t.Point, false) != t.Expected {
			fmt.Fprintf(os.Stderr, "[%s] source test failed at %v\n", c.Name, t.Point)
			os.Exit(2)
		}
	}
}

func verdictKey(divergence, dominance, common int) string {
	if divergence > 0 && dominance == 0 {
		return "p_strict_contains_q"
	}
	if dominance > 0 && divergence == 0 {
		return "q_strict_contains_p"
	}
	if divergence > 0 && dominance > 0 {
		return "parallel"
	}
	if common > 0 {
		return "equivalent"
	}
	return "disjoint"
}

func main() {
	specPath := flag.String("spec", "claims.json", "path to claims.json")
	mutant := flag.String("mutant", "", "mutant name (boundary)")
	flag.Parse()
	mutate := *mutant == "boundary"

	raw, err := os.ReadFile(*specPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "read spec: %v\n", err)
		os.Exit(2)
	}
	var spec Spec
	if err := json.Unmarshal(raw, &spec); err != nil {
		fmt.Fprintf(os.Stderr, "parse spec: %v\n", err)
		os.Exit(2)
	}
	if spec.SchemaVersion != 1 {
		fmt.Fprintf(os.Stderr, "unsupported schema_version %d\n", spec.SchemaVersion)
		os.Exit(2)
	}

	results := make([]Result, 0, len(spec.Pairs))
	match := true
	for _, pair := range spec.Pairs {
		guard(pair.P)
		guard(pair.Q)
		r := Result{ID: pair.ID}
		r.DivergenceWitness = []int{}
		r.DominanceWitness = []int{}
		for _, point := range spec.Domain {
			// The out-of-domain decision uses the same operators but ignores the mutant: the wrong port errs only in the predicate surface.
			if !evalOp(pair.P.Applies, point, false) || !evalOp(pair.Q.Applies, point, false) {
				r.OutOfDomain++
				continue
			}
			p := evalOp(pair.P.Predicate, point, mutate)
			q := evalOp(pair.Q.Predicate, point, mutate)
			switch {
			case p && q:
				r.Common++
			case p && !q:
				r.Divergence++
				if len(r.DivergenceWitness) < maxWitness {
					r.DivergenceWitness = append(r.DivergenceWitness, point["n"])
				}
			case !p && q:
				r.Dominance++
				if len(r.DominanceWitness) < maxWitness {
					r.DominanceWitness = append(r.DominanceWitness, point["n"])
				}
			default:
				r.Neither++
			}
		}
		r.Verdict = verdictKey(r.Divergence, r.Dominance, r.Common)
		if r.Common != pair.Expect.Common ||
			r.Divergence != pair.Expect.Divergence ||
			r.Dominance != pair.Expect.Dominance ||
			r.Neither != pair.Expect.Neither ||
			r.OutOfDomain != pair.Expect.OutOfDomain ||
			r.Verdict != pair.Expect.Verdict {
			match = false
		}
		results = append(results, r)
	}

	payload := struct {
		Results []Result `json:"results"`
		Match   bool     `json:"match_expect"`
	}{results, match}
	out, _ := json.Marshal(payload)
	fmt.Println(string(out))
	if !match {
		os.Exit(1)
	}
}
