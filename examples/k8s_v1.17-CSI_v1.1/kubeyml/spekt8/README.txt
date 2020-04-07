On the master:
 kubectl apply -f rbac.yml
 kubectl apply -f deploy.yml
 kubectl port-forward deployment/spekt8 192.168.10.90:3000:3000

Then on our host redirect the port:
 ssh -i ~/.ssh/vagrant_insecure_key -o "ProxyCommand ssh '192.168.1.11' -l 'geguileo' -i '/home/geguileo/.ssh/id_rsa' nc %h %p" -NL 3000:127.0.0.1:3000 vagrant@192.168.121.160

Then go to our browser to localhost:3000
