Several ways to connect:

2. Service logs (daemontools):

ssh r 'tail -f /var/log/inverter-control/current | tai64nlocal'
3. API requests:

# System state
ssh r 'curl -sk https://localhost:8080/api/state | python3 -m json.tool'
# Console (last lines)
ssh r 'curl -sk https://localhost:8080/api/console'
# History for graphs
ssh r 'curl -sk https://localhost:8080/api/history'
4. Service status:

ssh r 'svstat /service/inverter-control'
5. Service control:

ssh r 'svc -t /service/inverter-control'  # restart
ssh r 'svc -d /service/inverter-control'  # stop
ssh r 'svc -u /service/inverter-control'  # start
