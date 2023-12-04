// Powered by ChatGPT na cara dura.
package main

import (
	"fmt"
	"net"
	"os"
	"sync"
	"time"
)

func main() {
	var connectionLostTime time.Time
	var totalDowntime time.Duration
	var lastLoggedMonth time.Month

	for {
		if isConnected() {
			if !connectionLostTime.IsZero() {
				connectionReturnTime := time.Now()
				downtime := connectionReturnTime.Sub(connectionLostTime)
				totalDowntime += downtime
				logConnectionEvent(connectionLostTime, connectionReturnTime, downtime)
				connectionLostTime = time.Time{}
			}
		} else {
			if connectionLostTime.IsZero() {
				connectionLostTime = time.Now()
			}
		}

		if time.Now().Month() != lastLoggedMonth && time.Now().Format("02-15:04:05") == "30-23:59:59" {
			logMonthlyDowntime(time.Now(), totalDowntime)
			totalDowntime = 0
			lastLoggedMonth = time.Now().Month()
		}

		time.Sleep(100 * time.Millisecond) // Reduced sleep duration for more frequent checks
	}
}

func isConnected() bool {
	var wg sync.WaitGroup
	servers := []string{"8.8.8.8:53", "1.1.1.1:53", "9.9.9.9:53"}
	status := make(chan bool, len(servers))

	for _, server := range servers {
		wg.Add(1)
		go func(server string) {
			defer wg.Done()
			_, err := net.DialTimeout("tcp", server, 1*time.Second)
			status <- err == nil
		}(server)
	}

	go func() {
		wg.Wait()
		close(status)
	}()

	for isConnected := range status {
		if isConnected {
			return true
		}
	}
	return false
}


func logConnectionEvent(lostTime, returnTime time.Time, downtime time.Duration) {
	message := fmt.Sprintf("Connection lost at: %s\nConnection returned at: %s\nTotal downtime: %s\n",
		lostTime.Format("2006-01-02 15:04:05"),
		returnTime.Format("2006-01-02 15:04:05"),
		downtime)
	fmt.Print(message)
	appendToFile("connection_log.txt", message)
}

func logMonthlyDowntime(currentTime time.Time, totalDowntime time.Duration) {
	monthlyMessage := fmt.Sprintf("Month: %s\nTotal Downtime This Month: %s\n",
		currentTime.Format("January 2006"),
		totalDowntime)
	fmt.Print(monthlyMessage)
	appendToFile("connection_log.txt", monthlyMessage)
}

func appendToFile(filename, text string) {
	file, err := os.OpenFile(filename, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		fmt.Println("Error opening file:", err)
		return
	}
	defer file.Close()

	if _, err := file.WriteString(text); err != nil {
		fmt.Println("Error writing to file:", err)
	}
}
