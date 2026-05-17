.PHONY: plan apply deploy

plan:
	cd terraform && terraform plan -var="allowed_cidr=$$(curl -s -4 ifconfig.me)/32"

apply:
	cd terraform && terraform apply -var="allowed_cidr=$$(curl -s -4 ifconfig.me)/32"

deploy:
	aws ecs update-service --cluster moon --service moon --force-new-deployment

up:
	aws ecs update-service --cluster moon --service moon --desired-count 1

down:
	aws ecs update-service --cluster moon --service moon --desired-count 0
