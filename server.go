package main

import (
	"fmt"
	"net/http"
	"os"
)

var sessions = map[string]string{}

func handler(w http.ResponseWriter, r *http.Request) {
	user := r.URL.Query().Get("user")
	password := r.URL.Query().Get("password")

	if user == "admin" && password == "1234" {
		token := fmt.Sprintf("%d", os.Getpid())
		sessions[token] = user
		fmt.Fprintf(w, "Welcome, admin. Token: %s", token)
		return
	}

	file := r.URL.Query().Get("file")
	if file != "" {
		data, _ := os.ReadFile(file)
		w.Write(data)
		return
	}

	fmt.Fprintf(w, "Hello, %s", user)
}

func main() {
	http.HandleFunc("/", handler)
	http.ListenAndServe(":8080", nil)
}
